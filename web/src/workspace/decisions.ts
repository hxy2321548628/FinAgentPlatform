import type { InterruptAction } from '../api/events'
import type { Decision, DecisionType } from '../api/types'

export const DECISION_LABEL: Record<DecisionType, string> = {
  approve: '允许执行',
  reject: '拒绝',
  edit: '修改参数后执行',
  respond: '回复智能体',
}

export interface DecisionDraft {
  type: DecisionType | null
  message: string
  args: string
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

export function createDecisionDrafts(actions: InterruptAction[]): Record<number, DecisionDraft> {
  return Object.fromEntries(actions.map(action => [action.index, {
    type: null,
    message: '',
    args: JSON.stringify(action.args, null, 2),
  }]))
}

export function buildDecisions(
  actions: InterruptAction[],
  drafts: Record<number, DecisionDraft>,
): Decision[] {
  return actions.map(action => {
    const draft = drafts[action.index]
    if (!draft?.type) throw new Error(`请处理第 ${action.index + 1} 个待确认操作`)
    if (!action.allowed_decisions.includes(draft.type)) {
      throw new Error(`操作 ${action.index + 1} 不允许选择“${DECISION_LABEL[draft.type]}”`)
    }

    const decision: Decision = { index: action.index, type: draft.type }
    if (draft.type === 'reject' || draft.type === 'respond') {
      if (!draft.message.trim()) throw new Error(`${DECISION_LABEL[draft.type]}必须填写理由`)
      decision.message = draft.message.trim()
    }
    if (draft.type === 'edit') {
      let parsed: unknown
      try {
        parsed = JSON.parse(draft.args) as unknown
      } catch {
        throw new Error(`操作 ${action.index + 1} 的参数不是合法 JSON`)
      }
      if (!isRecord(parsed)) throw new Error(`操作 ${action.index + 1} 的参数必须是 JSON 对象`)
      decision.edited_action = { name: action.tool_name, args: parsed }
    }
    return decision
  })
}
