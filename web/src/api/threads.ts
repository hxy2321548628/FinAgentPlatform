import { request } from './request'
import type { AgentConfig, CursorPage, ThreadDetail, ThreadSummary } from './types'

export const threadKeys = {
  all: ['threads'] as const,
  list: (query = '') => ['threads', 'list', query] as const,
  detail: (threadId: string) => ['threads', 'detail', threadId] as const,
}

export function listThreads(cursor?: string | null, limit = 20, query = ''): Promise<CursorPage<ThreadSummary>> {
  const params = new URLSearchParams({ limit: String(limit) })
  if (cursor) params.set('cursor', cursor)
  if (query) params.set('q', query)
  return request(`/api/threads?${params}`)
}

export function createThread(): Promise<ThreadSummary> {
  return request('/api/threads', { method: 'POST' })
}

export function getThread(threadId: string): Promise<ThreadDetail> {
  return request(`/api/threads/${encodeURIComponent(threadId)}`)
}

export function updateThread(
  threadId: string,
  change: { title?: string; agent_config?: AgentConfig },
): Promise<ThreadDetail> {
  return request(`/api/threads/${encodeURIComponent(threadId)}`, { method: 'PATCH', json: change })
}

export function deleteThread(threadId: string): Promise<void> {
  return request(`/api/threads/${encodeURIComponent(threadId)}`, { method: 'DELETE' })
}
