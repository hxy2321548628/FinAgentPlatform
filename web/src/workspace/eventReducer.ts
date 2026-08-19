import type { InterruptAction, RunEvent, TodoItem, TokenUsage } from '../api/events'
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

/**
 * agent 自己维护的那张任务清单，只装在主图上，因此只有一张。
 *
 * 每条 `todo.updated` 都是整张清单，直接替换 —— 不做增量合并，那份合并逻辑
 * 与真相源不同步时不报错，只是进度显示得不对。
 */
export interface RunViewState {
  status: RunStatus
  items: RunViewItem[]
  todos: TodoItem[]
  pendingActions: InterruptAction[] | null
  tokens: TokenUsage | null
}

export type RunViewAction =
  | { kind: 'event'; event: RunEvent }
  | { kind: 'approval_submitted' }
  | { kind: 'status_synced'; status: RunStatus }
  | { kind: 'reset'; status: RunStatus }

/**
 * 清单工具的名字。**前后端各写一处，两边注释互指** ——
 * 后端在 `app/agent/todo.py`，那里同时是「清单只装主图」这条定案的落点。
 */
export const TODO_TOOL_NAME = 'write_todos'

export function createRunViewState(status: RunStatus): RunViewState {
  return { status, items: [], todos: [], pendingActions: null, tokens: null }
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
    // 清单那次调用没有卡片可补 —— 它的结果正文是英文的 `Updated todo list to [...]`，
    // 补一张就是同一件事显示两遍，一遍中文清单一遍英文工具卡
    if (event.data.name === TODO_TOOL_NAME) return items
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
    case 'compaction':
      // info 而不是 warning：压缩是正常机制，不是出了事。但必须显示 ——
      // 它是「后面的回答为什么像是忘了前面」的唯一解释
      return {
        ...state,
        items: [...state.items, {
          kind: 'notice',
          message: '对话变长，更早的内容已折成摘要，后续回答基于摘要而非原文',
          tone: 'info',
          path: event.path,
        }],
      }
    case 'token':
      return { ...state, items: appendDelta(state.items, 'answer', event.data.text, event.path) }
    case 'reasoning':
      return { ...state, items: appendDelta(state.items, 'reasoning', event.data.text, event.path) }
    case 'tool_call':
      // 清单不以工具卡片出现，它有自己的清单区 —— 教师要看的是进度，不是一次调用
      if (event.data.name === TODO_TOOL_NAME) return state
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
    case 'todo.updated':
      return { ...state, todos: event.data.todos }
    case 'interrupt':
      return { ...state, status: 'waiting_approval', pendingActions: event.data.actions }
  }
}
