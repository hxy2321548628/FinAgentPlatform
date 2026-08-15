import { request } from './request'
import type { FileContent, UploadResult, WorkspaceTree } from './types'

export const fileKeys = {
  tree: (threadId: string) => ['files', 'tree', threadId] as const,
  content: (threadId: string, path: string) => ['files', 'content', threadId, path] as const,
}

export function listFiles(threadId: string): Promise<WorkspaceTree> {
  return request(`/api/threads/${encodeURIComponent(threadId)}/files`)
}

export function readFile(threadId: string, path: string): Promise<FileContent> {
  const query = new URLSearchParams({ path })
  return request(`/api/threads/${encodeURIComponent(threadId)}/files/content?${query}`)
}

export function uploadFile(threadId: string, file: File, directory = ''): Promise<UploadResult> {
  const form = new FormData()
  form.append('file', file)
  form.append('directory', directory)
  return request(`/api/threads/${encodeURIComponent(threadId)}/files`, {
    method: 'POST',
    body: form,
  })
}

export function writeFile(threadId: string, path: string, text: string): Promise<void> {
  return request(`/api/threads/${encodeURIComponent(threadId)}/files/content`, {
    method: 'PUT',
    json: { path, text },
  })
}

export function createDirectory(threadId: string, path: string): Promise<void> {
  return request(`/api/threads/${encodeURIComponent(threadId)}/files/directory`, {
    method: 'POST',
    json: { path },
  })
}

export function deleteFile(threadId: string, path: string): Promise<void> {
  const query = new URLSearchParams({ path })
  return request(`/api/threads/${encodeURIComponent(threadId)}/files?${query}`, { method: 'DELETE' })
}

export function rawFileUrl(threadId: string, path: string, download = false): string {
  const query = new URLSearchParams({ path, download: String(download) })
  return `/api/threads/${encodeURIComponent(threadId)}/files/raw?${query}`
}
