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

export function approveRun(runId: string, decisions: Decision[]): Promise<RunSummary> {
  return request(`/api/runs/${encodeURIComponent(runId)}/approve`, {
    method: 'POST',
    json: { decisions },
  })
}
