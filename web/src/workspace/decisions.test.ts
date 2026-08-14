import { describe, expect, it } from 'vitest'
import type { InterruptAction } from '../api/events'
import { buildDecisions, createDecisionDrafts } from './decisions'

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
