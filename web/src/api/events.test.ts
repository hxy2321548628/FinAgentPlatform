import { describe, expect, it, vi } from 'vitest'
import {
  isRetryableRunEventError,
  isTerminalStatus,
  parseRunEvent,
  RUN_EVENT_NAMES,
  subscribeToRunEvents,
  type RunEventConnectionOptions,
  type RunEventTransport,
} from './events'

const validEventData = [
  ['run.started', { thread_id: 'thread-1', resumed: false }],
  ['run.finished', {
    status: 'succeeded',
    tokens: { input_cache_read: 1, input_uncached: 2, output: 3 },
  }],
  ['run.failed', { code: 'INTERNAL', message: '失败', retryable: true }],
  ['run.failed', { code: 'RECURSION_LIMIT', message: '这次分析走的步数超过了上限', retryable: false }],
  ['run.cancelled', { tokens: { input_cache_read: 1, input_uncached: 2, output: 3 } }],
  ['sandbox.queued', { position: 1 }],
  ['sandbox.ready', {}],
  ['error', { code: 'ORPHANED', message: '告警' }],
  ['compaction', { cutoff_index: 12, file_path: '/workspace/.compaction/history-1.md' }],
  ['compaction', { cutoff_index: 0, file_path: null }],
  ['token', { text: '答案' }],
  ['reasoning', { text: '思考' }],
  ['tool_call', { id: 'call-1', name: 'execute', args: { command: 'pwd' } }],
  ['tool_result', {
    tool_call_id: 'call-1', name: 'execute', content: 'ok', status: 'success',
  }],
  ['interrupt', { actions: [{
    index: 0,
    tool_name: 'delete',
    args: { path: 'old.csv' },
    allowed_decisions: ['approve', 'reject'],
  }] }],
] as const

function message(eventName: string, data: unknown, envelope: Record<string, unknown> = {}) {
  return {
    eventName,
    lastEventId: '10-0',
    data: JSON.stringify({
      type: eventName,
      ts: 1,
      run_id: 'run-1',
      path: [],
      data,
      ...envelope,
    }),
  }
}

describe('run event subscription', () => {
  it('registers all 16 named events and forwards a supported event', () => {
    let options: RunEventConnectionOptions | undefined
    const close = vi.fn()
    const transport: RunEventTransport = {
      connect(received) {
        options = received
        return { close }
      },
    }
    const onEvent = vi.fn()

    const connection = subscribeToRunEvents(transport, 'run-1', { allowEmptyClose: true, onEvent })

    expect(options?.eventNames).toEqual(RUN_EVENT_NAMES)
    expect(options?.url).toBe('/api/runs/run-1/events')
    expect(options?.allowEmptyClose).toBe(true)
    options?.onMessage({
      eventName: 'token',
      lastEventId: '10-0',
      data: JSON.stringify({
        type: 'token', ts: 1, run_id: 'run-1', path: [], data: { text: '喵' },
      }),
    })
    expect(onEvent).toHaveBeenCalledWith(expect.objectContaining({ type: 'token' }), '10-0')
    connection.close()
    expect(close).toHaveBeenCalledOnce()
  })

  it('ignores the three declared future events, unknown names and malformed payloads', () => {
    let options: RunEventConnectionOptions | undefined
    const transport: RunEventTransport = {
      connect(received) {
        options = received
        return { close() {} }
      },
    }
    const onEvent = vi.fn()
    subscribeToRunEvents(transport, 'run-1', { onEvent })

    for (const eventName of ['todo.updated', 'subagent.started', 'subagent.finished', 'new.event']) {
      options?.onMessage({
        eventName,
        lastEventId: '11-0',
        data: JSON.stringify({ type: eventName, ts: 1, run_id: 'run-1', path: [], data: {} }),
      })
    }
    options?.onMessage({ eventName: 'token', lastEventId: '12-0', data: '{' })
    expect(onEvent).not.toHaveBeenCalled()
  })

  it.each(validEventData)('validates the %s payload contract', (eventName, data) => {
    expect(parseRunEvent(message(eventName, data))).toMatchObject({ type: eventName, data })
  })

  it.each([
    ['run.started', { thread_id: 'thread-1', resumed: 'false' }],
    ['run.finished', {
      status: 'failed', tokens: { input_cache_read: 1, input_uncached: 2, output: 3 },
    }],
    ['run.finished', {
      status: 'succeeded', tokens: { input_cache_read: 1, input_uncached: 2, output: '3' },
    }],
    ['run.failed', { code: 'UNKNOWN', message: '失败', retryable: false }],
    ['run.failed', { code: 'INTERNAL', message: '失败', retryable: 0 }],
    ['run.cancelled', { tokens: { input_cache_read: -1, input_uncached: 2, output: 3 } }],
    ['sandbox.queued', { position: 0 }],
    ['sandbox.ready', { sandbox_id: 'unexpected' }],
    ['error', { code: 'INTERNAL', message: false }],
  ['compaction', { cutoff_index: -1, file_path: null }],
  ['compaction', { cutoff_index: '12', file_path: null }],
    ['token', { text: 1 }],
    ['reasoning', { text: false }],
    ['tool_call', { id: 'call-1', name: 'execute', args: [] }],
    ['tool_result', { tool_call_id: 'call-1', name: 'execute', content: 'ok', status: 'pending' }],
    ['interrupt', { actions: {} }],
    ['interrupt', { actions: [{
      index: '0',
      tool_name: 'delete',
      args: { path: 'old.csv' },
      allowed_decisions: ['approve'],
    }] }],
    ['interrupt', { actions: [{
      index: 0,
      tool_name: 'delete',
      args: [],
      allowed_decisions: ['approve'],
    }] }],
    ['interrupt', { actions: [{
      index: 0,
      tool_name: 'delete',
      args: {},
      allowed_decisions: ['approve', 1],
    }] }],
  ] as const)('rejects malformed %s data', (eventName, data) => {
    expect(parseRunEvent(message(eventName, data))).toBeNull()
  })

  it.each([
    { ts: '1' },
    { ts: 1.5 },
    { run_id: '' },
    { path: ['agent', 1] },
    { data: [] },
  ])('rejects a malformed envelope: %j', envelope => {
    expect(parseRunEvent(message('token', { text: '喂' }, envelope))).toBeNull()
  })

  it('rejects a payload whose envelope type does not match the named SSE event', () => {
    let options: RunEventConnectionOptions | undefined
    const transport: RunEventTransport = {
      connect(received) {
        options = received
        return { close() {} }
      },
    }
    const onEvent = vi.fn()
    subscribeToRunEvents(transport, 'run-1', { onEvent })
    options?.onMessage({
      eventName: 'token',
      lastEventId: '13-0',
      data: JSON.stringify({ type: 'reasoning', ts: 1, run_id: 'run-1', path: [], data: { text: 'x' } }),
    })
    expect(onEvent).not.toHaveBeenCalled()
  })

  it('does not forward malformed token or interrupt data to the reducer boundary', () => {
    let options: RunEventConnectionOptions | undefined
    const transport: RunEventTransport = {
      connect(received) {
        options = received
        return { close() {} }
      },
    }
    const onEvent = vi.fn()
    subscribeToRunEvents(transport, 'run-1', { onEvent })

    options?.onMessage(message('token', { text: 1 }))
    options?.onMessage(message('interrupt', { actions: [{
      index: 0,
      tool_name: 'delete',
      args: [],
      allowed_decisions: ['approve'],
    }] }))

    expect(onEvent).not.toHaveBeenCalled()
  })

  it('recognizes only terminal run states', () => {
    expect(isTerminalStatus('succeeded')).toBe(true)
    expect(isTerminalStatus('failed')).toBe(true)
    expect(isTerminalStatus('cancelled')).toBe(true)
    expect(isTerminalStatus('waiting_approval')).toBe(false)
  })

  it('treats only an explicit retryable=false connection error as fatal', () => {
    expect(isRetryableRunEventError(new Error('断线'))).toBe(true)
    expect(isRetryableRunEventError({ retryable: true })).toBe(true)
    expect(isRetryableRunEventError({ retryable: false })).toBe(false)
  })
})
