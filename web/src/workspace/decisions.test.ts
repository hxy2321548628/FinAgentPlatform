import { describe, expect, it } from 'vitest'
import type { InterruptAction } from '../api/events'
import { buildDecisions, createDecisionDrafts, isQuestion, QUESTION_TOOL_NAME, questionText } from './decisions'

const actions: InterruptAction[] = [
  { index: 0, tool_name: 'read', args: { path: 'a.csv' }, allowed_decisions: ['approve'] },
  { index: 1, tool_name: 'delete', args: { path: 'b.csv' }, allowed_decisions: ['reject'] },
  { index: 2, tool_name: 'write', args: { path: 'c.csv' }, allowed_decisions: ['edit'] },
  { index: 3, tool_name: 'ask', args: { topic: 'risk' }, allowed_decisions: ['respond'] },
]

describe('HITL decision batch', () => {
  it('builds one complete batch with all four decision types', () => {
    const drafts = createDecisionDrafts(actions)
    drafts[0].type = 'approve'
    drafts[1] = { ...drafts[1], type: 'reject', message: '不要删除原始数据' }
    drafts[2] = { ...drafts[2], type: 'edit', args: '{"path":"safe/c.csv"}' }
    drafts[3] = { ...drafts[3], type: 'respond', message: '改用月度收益率' }

    expect(buildDecisions(actions, drafts)).toEqual([
      { index: 0, type: 'approve' },
      { index: 1, type: 'reject', message: '不要删除原始数据' },
      { index: 2, type: 'edit', edited_action: { name: 'write', args: { path: 'safe/c.csv' } } },
      { index: 3, type: 'respond', message: '改用月度收益率' },
    ])
  })

  it.each(['reject', 'respond'] as const)('requires a reason for %s', type => {
    const one = [{ index: 0, tool_name: 'danger', args: {}, allowed_decisions: [type] }]
    const drafts = createDecisionDrafts(one)
    drafts[0].type = type

    expect(() => buildDecisions(one, drafts)).toThrow('必须填写理由')
  })

  it('asks the teacher to answer rather than to give a reason', () => {
    // 提问卡片上一句「回复智能体必须填写理由」不知所云 —— 它要的是那个口径
    const one = [{ index: 0, tool_name: QUESTION_TOOL_NAME, args: { question: '按日频还是月频？' }, allowed_decisions: ['respond'] }]

    expect(() => buildDecisions(one, createDecisionDrafts(one))).toThrow('请回答第 1 个问题')
  })

  it('preselects the only allowed decision so a question needs no extra click', () => {
    const one = [{ index: 0, tool_name: QUESTION_TOOL_NAME, args: {}, allowed_decisions: ['respond'] }]

    expect(createDecisionDrafts(one)[0].type).toBe('respond')
  })

  it('never preselects a decision that lets the call through', () => {
    // 「只允许一种」不是预选的理由：只允许 `approve` 的调用会默认停在「允许执行」上，
    // 而这道闸的全部意义就是让教师自己按下那一下
    expect(createDecisionDrafts([
      { index: 0, tool_name: 'delete', args: {}, allowed_decisions: ['approve'] },
    ])[0].type).toBeNull()
    expect(createDecisionDrafts([
      { index: 0, tool_name: 'delete', args: {}, allowed_decisions: ['approve', 'reject', 'edit', 'respond'] },
    ])[0].type).toBeNull()
  })

  it('reads the question text out of the tool args', () => {
    const action = { index: 0, tool_name: QUESTION_TOOL_NAME, args: { question: '按日频还是月频？' }, allowed_decisions: ['respond'] }

    expect(isQuestion(action)).toBe(true)
    expect(questionText(action)).toBe('按日频还是月频？')
  })

  it('does not mistake an approval for a question', () => {
    // **分流靠工具名这一个客观事实**，不靠新加的字段 —— 加字段等于造第二个真相源
    expect(isQuestion({ index: 0, tool_name: 'delete', args: {}, allowed_decisions: ['approve'] })).toBe(false)
  })

  it('requires edit args to be a JSON object', () => {
    const one = [{ index: 0, tool_name: 'write', args: {}, allowed_decisions: ['edit'] }]
    const drafts = createDecisionDrafts(one)
    drafts[0] = { ...drafts[0], type: 'edit', args: '[]' }
    expect(() => buildDecisions(one, drafts)).toThrow('必须是 JSON 对象')

    drafts[0].args = '{'
    expect(() => buildDecisions(one, drafts)).toThrow('不是合法 JSON')
  })

  it('rejects incomplete or disallowed batches', () => {
    const one = [{ index: 0, tool_name: 'read', args: {}, allowed_decisions: ['approve'] }]
    const drafts = createDecisionDrafts(one)
    expect(() => buildDecisions(one, drafts)).toThrow('请处理第 1 个')

    drafts[0].type = 'edit'
    expect(() => buildDecisions(one, drafts)).toThrow('不允许选择')
  })
})
