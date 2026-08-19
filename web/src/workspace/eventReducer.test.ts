import { describe, expect, it } from 'vitest'
import type { RunEvent } from '../api/events'
import { createRunViewState, runViewReducer } from './eventReducer'

function event<T extends RunEvent>(value: T): T {
  return value
}

describe('runViewReducer', () => {
  it('aggregates token and reasoning deltas without mixing paths', () => {
    let state = createRunViewState('queued')
    state = runViewReducer(state, { kind: 'event', event: event({
      type: 'reasoning', ts: 1, run_id: 'r1', path: [], data: { text: '思考' },
    }) })
    state = runViewReducer(state, { kind: 'event', event: event({
      type: 'reasoning', ts: 2, run_id: 'r1', path: [], data: { text: '中' },
    }) })
    state = runViewReducer(state, { kind: 'event', event: event({
      type: 'token', ts: 3, run_id: 'r1', path: [], data: { text: '结' },
    }) })
    state = runViewReducer(state, { kind: 'event', event: event({
      type: 'token', ts: 4, run_id: 'r1', path: [], data: { text: '论' },
    }) })
    state = runViewReducer(state, { kind: 'event', event: event({
      type: 'token', ts: 5, run_id: 'r1', path: ['child'], data: { text: '子任务' },
    }) })

    expect(state.items).toMatchObject([
      { kind: 'reasoning', text: '思考中', path: [] },
      { kind: 'answer', text: '结论', path: [] },
      { kind: 'answer', text: '子任务', path: ['child'] },
    ])
  })

  it('pairs tool results by call id', () => {
    let state = createRunViewState('running')
    state = runViewReducer(state, { kind: 'event', event: event({
      type: 'tool_call', ts: 1, run_id: 'r1', path: [],
      data: { id: 'call-1', name: 'delete', args: { path: 'old.csv' } },
    }) })
    state = runViewReducer(state, { kind: 'event', event: event({
      type: 'tool_result', ts: 2, run_id: 'r1', path: [],
      data: { tool_call_id: 'call-1', name: 'delete', content: 'ok', status: 'success' },
    }) })
    expect(state.items[0]).toMatchObject({
      kind: 'tool', id: 'call-1', status: 'success', content: 'ok',
    })
  })

  it('keeps prior output on resume and exposes a whole interrupt batch', () => {
    let state = createRunViewState('running')
    state = runViewReducer(state, { kind: 'event', event: event({
      type: 'token', ts: 1, run_id: 'r1', path: [], data: { text: '已完成的内容' },
    }) })
    state = runViewReducer(state, { kind: 'event', event: event({
      type: 'interrupt', ts: 2, run_id: 'r1', path: [], data: { actions: [
        { index: 0, tool_name: 'delete', args: { path: 'a' }, allowed_decisions: ['approve', 'reject'] },
        { index: 1, tool_name: 'delete', args: { path: 'b' }, allowed_decisions: ['edit', 'respond'] },
      ] },
    }) })
    expect(state.status).toBe('waiting_approval')
    expect(state.pendingActions).toHaveLength(2)

    state = runViewReducer(state, { kind: 'event', event: event({
      type: 'run.started', ts: 3, run_id: 'r1', path: [], data: { thread_id: 't1', resumed: true },
    }) })
    expect(state.status).toBe('running')
    expect(state.pendingActions).toBeNull()
    expect(state.items).toMatchObject([{ kind: 'answer', text: '已完成的内容' }])
  })

  it('shows compaction as an informational notice, not an error', () => {
    // 压缩是长对话里的正常机制。记成 error 会让教师白紧张一次，
    // 而完全不显示则解释不了「后面的回答怎么忘了前面说过的话」
    let state = createRunViewState('running')
    state = runViewReducer(state, { kind: 'event', event: event({
      type: 'compaction', ts: 1, run_id: 'r1', path: [],
      data: { cutoff_index: 12, file_path: '/workspace/.compaction/history-1.md' },
    }) })

    expect(state.status).toBe('running')
    expect(state.items).toMatchObject([{ kind: 'notice', tone: 'info' }])
    expect((state.items[0] as { message: string }).message).toContain('摘要')
  })

  it('records terminal state and nonfatal errors', () => {
    let state = createRunViewState('running')
    state = runViewReducer(state, { kind: 'event', event: event({
      type: 'error', ts: 1, run_id: 'r1', path: [],
      data: { code: 'INTERNAL', message: '一次可恢复告警' },
    }) })
    state = runViewReducer(state, { kind: 'event', event: event({
      type: 'run.finished', ts: 2, run_id: 'r1', path: [],
      data: { status: 'succeeded', tokens: { input_cache_read: 1, input_uncached: 2, output: 3 } },
    }) })
    expect(state.status).toBe('succeeded')
    expect(state.items).toMatchObject([{ kind: 'notice', message: '一次可恢复告警' }])
    expect(state.tokens).toEqual({ input_cache_read: 1, input_uncached: 2, output: 3 })
  })
})

describe('任务清单', () => {
  it('每条 todo.updated 都整张替换，最后一条就是当前清单', () => {
    let state = createRunViewState('running')
    state = runViewReducer(state, { kind: 'event', event: event({
      type: 'todo.updated', ts: 1, run_id: 'r1', path: [],
      data: { todos: [{ content: '读取数据', status: 'in_progress' }, { content: '算波动率', status: 'pending' }] },
    }) })
    state = runViewReducer(state, { kind: 'event', event: event({
      type: 'todo.updated', ts: 2, run_id: 'r1', path: [],
      data: { todos: [{ content: '读取数据', status: 'completed' }, { content: '算波动率', status: 'in_progress' }] },
    }) })

    expect(state.todos).toEqual([
      { content: '读取数据', status: 'completed' },
      { content: '算波动率', status: 'in_progress' },
    ])
  })

  it('收编 write_todos 那张工具卡片，同一件事不显示两遍', () => {
    // 不收编的话教师会同时看到一张中文清单，和一张正文是英文
    // `Updated todo list to [...]` 的工具卡
    let state = createRunViewState('running')
    state = runViewReducer(state, { kind: 'event', event: event({
      type: 'tool_call', ts: 1, run_id: 'r1', path: [],
      data: { id: 'call-todo', name: 'write_todos', args: { todos: [] } },
    }) })
    state = runViewReducer(state, { kind: 'event', event: event({
      type: 'tool_result', ts: 2, run_id: 'r1', path: [],
      data: { tool_call_id: 'call-todo', name: 'write_todos', content: 'Updated todo list to [...]', status: 'success' },
    }) })

    expect(state.items).toEqual([])
  })

  it('别的工具照旧出卡片 —— 收编只针对清单那一个', () => {
    let state = createRunViewState('running')
    state = runViewReducer(state, { kind: 'event', event: event({
      type: 'tool_call', ts: 1, run_id: 'r1', path: [],
      data: { id: 'call-1', name: 'write_file', args: { file_path: 'a.py' } },
    }) })

    expect(state.items).toHaveLength(1)
  })
})
