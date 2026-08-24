import { request } from './request'
import type { MemoryDetail, MemoryListResponse } from './types'

export const memoryKeys = {
  all: (threadId: string) => ['memories', threadId] as const,
  list: (threadId: string) => ['memories', threadId, 'list'] as const,
  detail: (threadId: string, slug: string) => ['memories', threadId, 'detail', slug] as const,
}

export function listMemories(threadId: string): Promise<MemoryListResponse> {
  return request(`/api/threads/${encodeURIComponent(threadId)}/memories`)
}

export function getMemory(threadId: string, slug: string): Promise<MemoryDetail> {
  return request(`/api/threads/${encodeURIComponent(threadId)}/memories/${encodeURIComponent(slug)}`)
}

export function deleteMemory(threadId: string, slug: string): Promise<void> {
  return request(`/api/threads/${encodeURIComponent(threadId)}/memories/${encodeURIComponent(slug)}`, {
    method: 'DELETE',
  })
}
