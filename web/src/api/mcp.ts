import { request } from './request'
import type { AdminMcpServer, McpProbe, McpServer, McpTransport } from './types'

export const mcpKeys = {
  all: ['mcp'] as const,
  catalog: () => ['mcp', 'catalog'] as const,
  admin: () => ['mcp', 'admin'] as const,
}

export interface McpApplication {
  name: string
  description: string
  url: string
  transport: McpTransport
  credential_key?: string | null
  tool_names: string[]
  latency_note: string
  stores_user_data: boolean
  sends_data_out: boolean
  has_write_operation: boolean
}

/** 目录：**只有管理员放行了的**。放行了就人人可勾，没有三档可见性。 */
export function listCatalog(): Promise<McpServer[]> {
  return request('/api/mcp')
}

export function applyForMcp(application: McpApplication): Promise<McpServer> {
  return request('/api/mcp', { method: 'POST', json: application })
}

/** 管理员后台：待审、已上架、已停用、已拒全都在里面。 */
export function listForAdmin(): Promise<AdminMcpServer[]> {
  return request('/api/mcp/admin')
}

export function decideApplication(serverId: string, approved: boolean, reason?: string): Promise<AdminMcpServer> {
  return request(`/api/mcp/admin/${encodeURIComponent(serverId)}/decision`, {
    method: 'POST',
    json: { approved, reason },
  })
}

export function setEnabled(serverId: string, enabled: boolean, reason?: string): Promise<AdminMcpServer> {
  return request(`/api/mcp/admin/${encodeURIComponent(serverId)}/enabled`, {
    method: 'POST',
    json: { enabled, reason },
  })
}

/** 测试连接。走的是装配同一条路与同一个熔断计数器 —— 连续失败到阈值一样会自动停用。 */
export function probe(serverId: string): Promise<McpProbe> {
  return request(`/api/mcp/admin/${encodeURIComponent(serverId)}/probe`, { method: 'POST' })
}
