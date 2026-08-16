import { type RunEvent, validateRunEvent } from './events'
import { request } from './request'
import type { AgentConfig, CursorPage, Decision, RunHistory, RunSummary } from './types'

export const runKeys = {
  all: ['runs'] as const,
  list: (threadId: string) => ['runs', 'list', threadId] as const,
  detail: (runId: string) => ['runs', 'detail', runId] as const,
}

export function listRuns(threadId: string, cursor?: string | null, limit = 20): Promise<CursorPage<RunHistory>> {
  const query = new URLSearchParams({ limit: String(limit) })
  if (cursor) query.set('cursor', cursor)
  return request(`/api/threads/${encodeURIComponent(threadId)}/runs?${query}`)
}

export function submitRun(
  threadId: string,
  content: string,
  agentConfig: AgentConfig | undefined,
): Promise<RunSummary> {
  const payload: { content: string; agent_config?: AgentConfig } = { content }
  if (agentConfig !== undefined) payload.agent_config = agentConfig
  return request(`/api/threads/${encodeURIComponent(threadId)}/runs`, {
    method: 'POST',
    json: payload,
  })
}

export function getRun(runId: string): Promise<RunSummary> {
  return request(`/api/runs/${encodeURIComponent(runId)}`)
}

export function cancelRun(runId: string): Promise<RunSummary> {
  return request(`/api/runs/${encodeURIComponent(runId)}/cancel`, { method: 'POST' })
}

export interface ReplayedRunEvent {
  id: string
  event: RunEvent
}

interface ReplayBody {
  items: { id: string; event: unknown }[]
}

/**
 * 一次取回一个 run 的全部过程，给已经结束的那些用。
 *
 * 它们不会再产生事件，而订阅是为「新事件一产生就推过来」建的：断了要重连，
 * 重连又要过一次频率闸。这条路读完即止，失败就是失败。
 *
 * 认不出的事件直接丢掉，与事件流那条路一致 —— 前端认不出的事件本来就渲染不了，
 * 而让整轮历史因为其中一条的形状不对而失败，代价大得多。
 */
export async function fetchRunReplay(runId: string): Promise<ReplayedRunEvent[]> {
  const body = await request<ReplayBody>(`/api/runs/${encodeURIComponent(runId)}/replay`)
  const replayed: ReplayedRunEvent[] = []
  for (const item of body.items) {
    const event = validateRunEvent(item.event)
    if (event) replayed.push({ id: item.id, event })
  }
  return replayed
}

export function approveRun(runId: string, decisions: Decision[]): Promise<RunSummary> {
  return request(`/api/runs/${encodeURIComponent(runId)}/approve`, {
    method: 'POST',
    json: { decisions },
  })
}
