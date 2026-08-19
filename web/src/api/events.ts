import type { RunErrorCode, RunStatus } from './types'

export const RUN_EVENT_NAMES = [
  'run.started',
  'run.finished',
  'run.failed',
  'run.cancelled',
  'sandbox.queued',
  'sandbox.ready',
  'error',
  'token',
  'reasoning',
  'tool_call',
  'tool_result',
  'todo.updated',
  'subagent.started',
  'subagent.finished',
  'interrupt',
  'compaction',
] as const

export type RunEventName = (typeof RUN_EVENT_NAMES)[number]

const SUPPORTED_EVENT_NAMES = [
  'run.started',
  'run.finished',
  'run.failed',
  'run.cancelled',
  'sandbox.queued',
  'sandbox.ready',
  'error',
  'token',
  'reasoning',
  'tool_call',
  'tool_result',
  'interrupt',
  'compaction',
] as const

type SupportedEventName = (typeof SUPPORTED_EVENT_NAMES)[number]

export interface TokenUsage {
  input_cache_read: number
  input_uncached: number
  output: number
}

export interface InterruptAction {
  index: number
  tool_name: string
  args: Record<string, unknown>
  allowed_decisions: string[]
}

interface EventEnvelope<Type extends SupportedEventName, Data> {
  type: Type
  ts: number
  run_id: string
  path: string[]
  data: Data
}

export type RunEvent =
  | EventEnvelope<'run.started', { thread_id: string; resumed: boolean }>
  | EventEnvelope<'run.finished', { status: 'succeeded'; tokens: TokenUsage }>
  | EventEnvelope<'run.failed', { code: RunErrorCode; message: string; retryable: boolean }>
  | EventEnvelope<'run.cancelled', { tokens: TokenUsage }>
  | EventEnvelope<'sandbox.queued', { position: number }>
  | EventEnvelope<'sandbox.ready', Record<string, never>>
  | EventEnvelope<'error', { code: RunErrorCode; message: string }>
  | EventEnvelope<'token', { text: string }>
  | EventEnvelope<'reasoning', { text: string }>
  | EventEnvelope<'tool_call', { id: string; name: string; args: Record<string, unknown> }>
  | EventEnvelope<'tool_result', {
      tool_call_id: string
      name: string
      content: string
      status: 'success' | 'error'
    }>
  | EventEnvelope<'interrupt', { actions: InterruptAction[] }>
  /** 上下文被折成了摘要。**不是错误** —— 长对话里的正常机制，但之后的回答基于摘要而非原文。 */
  | EventEnvelope<'compaction', { cutoff_index: number; file_path: string | null }>

export interface NamedRunEventMessage {
  eventName: string
  data: string
  lastEventId: string
}

export interface RunEventConnection {
  close(): void
}

export interface RunEventConnectionOptions {
  url: string
  eventNames: readonly RunEventName[]
  cursor?: string
  /** 仅当当前 HTTP attempt 没有收到事件帧时，clean EOF 才是正常收尾。 */
  allowEmptyClose?: boolean
  onMessage(message: NamedRunEventMessage): void
  onError?(error: unknown): void
  onOpen?(): void
}

export interface RunEventTransport {
  connect(options: RunEventConnectionOptions): RunEventConnection
}

const RUN_ERROR_CODES: readonly RunErrorCode[] = [
  'SANDBOX_QUEUE_TIMEOUT',
  'ORPHANED',
  'INTERNAL',
  'RECURSION_LIMIT',
]

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

export function isRetryableRunEventError(error: unknown): boolean {
  return !isRecord(error) || error.retryable !== false
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value.length > 0
}

function isInteger(value: unknown): value is number {
  return typeof value === 'number' && Number.isInteger(value)
}

function isNonNegativeInteger(value: unknown): value is number {
  return isInteger(value) && value >= 0
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(item => typeof item === 'string')
}

function isRunErrorCode(value: unknown): value is RunErrorCode {
  return typeof value === 'string' && RUN_ERROR_CODES.includes(value as RunErrorCode)
}

function isTokenUsage(value: unknown): value is TokenUsage {
  return isRecord(value)
    && isNonNegativeInteger(value.input_cache_read)
    && isNonNegativeInteger(value.input_uncached)
    && isNonNegativeInteger(value.output)
}

function isInterruptAction(value: unknown): value is InterruptAction {
  return isRecord(value)
    && isNonNegativeInteger(value.index)
    && isNonEmptyString(value.tool_name)
    && isRecord(value.args)
    && isStringArray(value.allowed_decisions)
}

function isSupportedEventData(eventName: SupportedEventName, data: Record<string, unknown>): boolean {
  switch (eventName) {
    case 'run.started':
      return isNonEmptyString(data.thread_id) && typeof data.resumed === 'boolean'
    case 'run.finished':
      return data.status === 'succeeded' && isTokenUsage(data.tokens)
    case 'run.failed':
      return isRunErrorCode(data.code)
        && isNonEmptyString(data.message)
        && typeof data.retryable === 'boolean'
    case 'run.cancelled':
      return isTokenUsage(data.tokens)
    case 'sandbox.queued':
      return isInteger(data.position) && data.position >= 1
    case 'sandbox.ready':
      return Object.keys(data).length === 0
    case 'error':
      return isRunErrorCode(data.code) && isNonEmptyString(data.message)
    case 'token':
    case 'reasoning':
      return isNonEmptyString(data.text)
    case 'tool_call':
      return typeof data.id === 'string'
        && isNonEmptyString(data.name)
        && isRecord(data.args)
    case 'tool_result':
      return typeof data.tool_call_id === 'string'
        && typeof data.name === 'string'
        && typeof data.content === 'string'
        && (data.status === 'success' || data.status === 'error')
    case 'interrupt':
      return Array.isArray(data.actions) && data.actions.every(isInterruptAction)
    case 'compaction':
      return isInteger(data.cutoff_index)
        && data.cutoff_index >= 0
        && (data.file_path === null || typeof data.file_path === 'string')
  }
}

function isSupportedEventName(value: unknown): value is SupportedEventName {
  return typeof value === 'string' && (SUPPORTED_EVENT_NAMES as readonly string[]).includes(value)
}

/**
 * 校验一个已经解析好的事件对象。
 *
 * 事件流给的是 SSE 报文里的一行文本，一次性回放给的是 JSON 里的一个对象 ——
 * 两条路的载荷形状是同一份契约，因此校验只有这一处。
 */
export function validateRunEvent(value: unknown): RunEvent | null {
  if (!isRecord(value)) return null
  const eventName = value.type
  if (!isSupportedEventName(eventName)) return null
  if (!isInteger(value.ts) || !isNonEmptyString(value.run_id)) return null
  if (!isStringArray(value.path) || !isRecord(value.data)) return null
  if (!isSupportedEventData(eventName, value.data)) return null
  return value as unknown as RunEvent
}

export function parseRunEvent(message: NamedRunEventMessage): RunEvent | null {
  if (!isSupportedEventName(message.eventName)) return null
  try {
    const parsed: unknown = JSON.parse(message.data)
    // event 行与 data 里的 type 必须一致：不一致时按哪一个渲染都是猜
    if (!isRecord(parsed) || parsed.type !== message.eventName) return null
    return validateRunEvent(parsed)
  } catch {
    return null
  }
}

export function subscribeToRunEvents(
  transport: RunEventTransport,
  runId: string,
  handlers: {
    cursor?: string
    allowEmptyClose?: boolean
    onEvent(event: RunEvent, lastEventId: string): void
    onError?(error: unknown): void
    onOpen?(): void
  },
): RunEventConnection {
  return transport.connect({
    url: `/api/runs/${encodeURIComponent(runId)}/events`,
    eventNames: RUN_EVENT_NAMES,
    cursor: handlers.cursor,
    allowEmptyClose: handlers.allowEmptyClose,
    onError: handlers.onError,
    onOpen: handlers.onOpen,
    onMessage(message) {
      const event = parseRunEvent(message)
      if (event) handlers.onEvent(event, message.lastEventId)
    },
  })
}

export function isTerminalStatus(status: RunStatus): boolean {
  return status === 'succeeded' || status === 'failed' || status === 'cancelled'
}
