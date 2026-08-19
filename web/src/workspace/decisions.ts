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

/**
 * 提问工具的名字。**前后端各写一处，两边注释互指** ——
 * 后端在 `app/agent/question.py`，那里同时是 `INTERRUPT_ON` 只给它 `respond` 的落点。
 *
 * 分流用工具名而不是新加一个 `kind` 字段：工具名就是那个客观事实，
 * 加字段等于在事件流之外再造一个真相源。
 */
export const QUESTION_TOOL_NAME = 'ask_user_question'

/** 提问工具里那个装着问题原文的参数名。 */
export const QUESTION_ARG = 'question'

export function isQuestion(action: InterruptAction): boolean {
  return action.tool_name === QUESTION_TOOL_NAME
}

export function questionText(action: InterruptAction): string {
  const value = action.args[QUESTION_ARG]
  return typeof value === 'string' && value.length > 0 ? value : '智能体想问你一个问题，但没写清楚问题本身。'
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/**
 * 只能回复时替教师把决策选好，让他直接写答案。
 *
 * **只对 `respond` 这一种预选。** 「只允许一种决策」听着是同一件事，但按它做的话，
 * 一个只允许 `approve` 的调用就会默认停在「允许执行」上 —— 预选一个放行决策
 * 是往危险的方向省一步，而这道闸的全部意义就是让教师自己按下那一下。
 */
function defaultType(action: InterruptAction): DecisionType | null {
  return action.allowed_decisions.length === 1 && action.allowed_decisions[0] === 'respond' ? 'respond' : null
}

export function createDecisionDrafts(actions: InterruptAction[]): Record<number, DecisionDraft> {
  return Object.fromEntries(actions.map(action => [action.index, {
    type: defaultType(action),
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
      if (!draft.message.trim()) {
        // 提问与拒绝要填的不是同一样东西，一句「必须填写理由」放在提问卡片上不知所云
        throw new Error(isQuestion(action) ? `请回答第 ${action.index + 1} 个问题` : `${DECISION_LABEL[draft.type]}必须填写理由`)
      }
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
