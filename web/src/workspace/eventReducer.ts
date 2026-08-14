import type { InterruptAction, RunEvent, TokenUsage } from '../api/events'
import type { RunStatus } from '../api/types'

interface BaseItem {
  path: string[]
}

export interface ReasoningItem extends BaseItem {
  kind: 'reasoning'
  text: string
}

export interface AnswerItem extends BaseItem {
  kind: 'answer'
  text: string
}

export interface ToolItem extends BaseItem {
  kind: 'tool'
  id: string
  name: string
  args: Record<string, unknown>
  content?: string
  status: 'running' | 'success' | 'error'
}

export interface NoticeItem extends BaseItem {
  kind: 'notice'
  message: string
  tone: 'info' | 'warning' | 'error'
}

export type RunViewItem = ReasoningItem | AnswerItem | ToolItem | NoticeItem

export interface RunViewState {
  status: RunStatus
  items: RunViewItem[]
  pendingActions: InterruptAction[] | null
  tokens: TokenUsage | null
}

export type RunViewAction =
  | { kind: 'event'; event: RunEvent }
  | { kind: 'approval_submitted' }
  | { kind: 'status_synced'; status: RunStatus }
  | { kind: 'reset'; status: RunStatus }

export function createRunViewState(status: RunStatus): RunViewState {
  return { status, items: [], pendingActions: null, tokens: null }
}

function samePath(left: string[], right: string[]): boolean {
  return left.length === right.length && left.every((part, index) => part === right[index])
}

function appendDelta(
  items: RunViewItem[],
  kind: 'answer' | 'reasoning',
  text: string,
  path: string[],
): RunViewItem[] {
  const last = items.at(-1)
  if (last?.kind === kind && samePath(last.path, path)) {
    return [...items.slice(0, -1), { ...last, text: last.text + text }]
  }
  return [...items, { kind, text, path }]
}

function updateTool(items: RunViewItem[], event: Extract<RunEvent, { type: 'tool_result' }>): RunViewItem[] {
  const index = items.findIndex(item => item.kind === 'tool' && item.id === event.data.tool_call_id)
  if (index < 0) {
    return [...items, {
      kind: 'tool',
      id: event.data.tool_call_id,
      name: event.data.name,
      args: {},
      content: event.data.content,
      status: event.data.status,
      path: event.path,
    }]
  }
  const item = items[index]
  if (item.kind !== 'tool') return items
  const changed: ToolItem = { ...item, content: event.data.content, status: event.data.status }
  return [...items.slice(0, index), changed, ...items.slice(index + 1)]
}

export function runViewReducer(state: RunViewState, action: RunViewAction): RunViewState {
  if (action.kind === 'reset') return createRunViewState(action.status)
  if (action.kind === 'status_synced') return { ...state, status: action.status }
  if (action.kind === 'approval_submitted') {
    return { ...state, status: 'queued', pendingActions: null }
  }

  const event = action.event
  switch (event.type) {
    case 'run.started':
      return { ...state, status: 'running', pendingActions: null }
    case 'run.finished':
      return { ...state, status: 'succeeded', tokens: event.data.tokens, pendingActions: null }
    case 'run.failed':
      return {
        ...state,
        status: 'failed',
        pendingActions: null,
        items: [...state.items, { kind: 'notice', message: event.data.message, tone: 'error', path: event.path }],
      }
    case 'run.cancelled':
      return { ...state, status: 'cancelled', tokens: event.data.tokens, pendingActions: null }
    case 'sandbox.queued':
      return {
        ...state,
        items: [...state.items, {
          kind: 'notice', message: `沙箱排队中，当前第 ${event.data.position} 位`, tone: 'info', path: event.path,
        }],
      }
    case 'sandbox.ready':
      return state
    case 'error':
      return {
        ...state,
        items: [...state.items, { kind: 'notice', message: event.data.message, tone: 'warning', path: event.path }],
      }
    case 'token':
      return { ...state, items: appendDelta(state.items, 'answer', event.data.text, event.path) }
    case 'reasoning':
      return { ...state, items: appendDelta(state.items, 'reasoning', event.data.text, event.path) }
    case 'tool_call':
      return {
        ...state,
        items: [...state.items, {
          kind: 'tool',
          id: event.data.id,
          name: event.data.name,
          args: event.data.args,
          status: 'running',
          path: event.path,
        }],
      }
    case 'tool_result':
      return { ...state, items: updateTool(state.items, event) }
    case 'interrupt':
      return { ...state, status: 'waiting_approval', pendingActions: event.data.actions }
  }
}
