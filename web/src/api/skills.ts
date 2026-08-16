import { request } from './request'
import type { MySkill, SkillFileContent, SkillFileEntry, SkillListing, Visibility } from './types'

export const skillKeys = {
  all: ['skills'] as const,
  catalog: () => ['skills', 'catalog'] as const,
  available: () => ['skills', 'available'] as const,
  mine: () => ['skills', 'mine'] as const,
  detail: (skillId: string) => ['skills', 'mine', skillId] as const,
  files: (skillId: string, version: number) => ['skills', skillId, 'versions', version, 'files'] as const,
  file: (skillId: string, version: number, path: string) => ['skills', skillId, 'versions', version, 'files', path] as const,
}

export function listCatalog(): Promise<SkillListing[]> {
  return request('/api/skills')
}

export function listAvailable(): Promise<SkillListing[]> {
  return request('/api/skills/available')
}

export function listVersionFiles(skillId: string, version: number): Promise<SkillFileEntry[]> {
  return request(`/api/skills/${encodeURIComponent(skillId)}/versions/${version}/files`)
}

export function readVersionFile(skillId: string, version: number, path: string): Promise<SkillFileContent> {
  const params = new URLSearchParams({ path })
  return request(`/api/skills/${encodeURIComponent(skillId)}/versions/${version}/files/content?${params}`)
}

export function listMine(): Promise<MySkill[]> {
  return request('/api/skills/mine')
}

export function getMine(skillId: string): Promise<MySkill> {
  return request(`/api/skills/mine/${encodeURIComponent(skillId)}`)
}

function packageForm(file: File, subject?: string): FormData {
  const form = new FormData()
  form.append('file', file)
  if (subject !== undefined) form.append('subject', subject)
  return form
}

export function createSkill(file: File, subject: string): Promise<MySkill> {
  return request('/api/skills', { method: 'POST', body: packageForm(file, subject) })
}

export function writeDraft(skillId: string, file: File): Promise<MySkill> {
  return request(`/api/skills/${encodeURIComponent(skillId)}/draft`, {
    method: 'POST',
    body: packageForm(file),
  })
}

export function updateSkill(skillId: string, subject: string): Promise<MySkill> {
  return request(`/api/skills/${encodeURIComponent(skillId)}`, { method: 'PATCH', json: { subject } })
}

export function releaseVersion(skillId: string): Promise<MySkill> {
  return request(`/api/skills/${encodeURIComponent(skillId)}/versions`, { method: 'POST' })
}

export function setSharing(skillId: string, visibility: Visibility, groupIds: string[]): Promise<MySkill> {
  return request(`/api/skills/${encodeURIComponent(skillId)}/sharing`, {
    method: 'PUT',
    json: { visibility, group_ids: groupIds },
  })
}

export function submitForReview(skillId: string, responsibilityConfirmed: boolean): Promise<MySkill> {
  return request(`/api/skills/${encodeURIComponent(skillId)}/reviews`, {
    method: 'POST',
    json: { responsibility_confirmed: responsibilityConfirmed },
  })
}

export function deleteSkill(skillId: string): Promise<void> {
  return request(`/api/skills/${encodeURIComponent(skillId)}`, { method: 'DELETE' })
}
