import { request } from './request'
import type { AgentListing, MyAgent, Visibility } from './types'

export const agentKeys = {
  all: ['agents'] as const,
  catalog: () => ['agents', 'catalog'] as const,
  available: () => ['agents', 'available'] as const,
  mine: () => ['agents', 'mine'] as const,
  detail: (agentId: string) => ['agents', 'mine', agentId] as const,
}

/** 广场：只有平台目录里的那些，展示的是最新那个**过审**的版本。 */
export function listCatalog(): Promise<AgentListing[]> {
  return request('/api/agents')
}

/** 我此刻能引用的：我自己的 ∪ 共享给我所在组的 ∪ 平台目录。 */
export function listAvailable(): Promise<AgentListing[]> {
  return request('/api/agents/available')
}

/** 我的全部，**含删掉的那些**（由 `is_deleted` 标出）。 */
export function listMine(): Promise<MyAgent[]> {
  return request('/api/agents/mine')
}

export function getMine(agentId: string): Promise<MyAgent> {
  return request(`/api/agents/mine/${encodeURIComponent(agentId)}`)
}

export function createAgent(body: {
  name: string
  description: string
  subject: string
  system_prompt: string
  skills?: string[]
}): Promise<MyAgent> {
  return request('/api/agents', { method: 'POST', json: body })
}

export function updateAgent(
  agentId: string,
  body: { name: string; description: string; subject: string },
): Promise<MyAgent> {
  return request(`/api/agents/${encodeURIComponent(agentId)}`, { method: 'PATCH', json: body })
}

/** 改草稿。已经定稿的话，这一下会追加下一个版本号的新草稿。 */
export function writeDraft(agentId: string, systemPrompt: string, skills: string[] = []): Promise<MyAgent> {
  return request(`/api/agents/${encodeURIComponent(agentId)}/draft`, {
    method: 'PUT',
    json: { system_prompt: systemPrompt, skills },
  })
}

/** 把草稿定稿。从这一刻起组员看得见它，进不进广场是另一回事。 */
export function releaseVersion(agentId: string): Promise<MyAgent> {
  return request(`/api/agents/${encodeURIComponent(agentId)}/versions`, { method: 'POST' })
}

export function setSharing(agentId: string, visibility: Visibility, groupIds: string[]): Promise<MyAgent> {
  return request(`/api/agents/${encodeURIComponent(agentId)}/sharing`, {
    method: 'PUT',
    json: { visibility, group_ids: groupIds },
  })
}

/** 提审最新那个已发布的版本。**没勾责任确认后端也会拒**。 */
export function submitForReview(agentId: string, responsibilityConfirmed: boolean): Promise<MyAgent> {
  return request(`/api/agents/${encodeURIComponent(agentId)}/reviews`, {
    method: 'POST',
    json: { responsibility_confirmed: responsibilityConfirmed },
  })
}

export function deleteAgent(agentId: string): Promise<void> {
  return request(`/api/agents/${encodeURIComponent(agentId)}`, { method: 'DELETE' })
}
