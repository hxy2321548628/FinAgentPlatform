import { request } from './request'
import type { AdminUser, SystemStatus, UserRole } from './types'

export const adminKeys = {
  users: () => ['admin', 'users'] as const,
  system: () => ['admin', 'system'] as const,
}

export function listUsers(): Promise<AdminUser[]> {
  return request('/api/admin/users')
}

export function createUser(body: {
  name: string
  email: string
  password: string
  role: UserRole
  dept?: string
}): Promise<AdminUser> {
  return request('/api/admin/users', { method: 'POST', json: body })
}

/**
 * 改一个账号，**只动传了的那几项**。
 *
 * 配额两项显式传 `null` 表示「回到角色默认档」，与「这一项不改」是两件事 ——
 * 后者是根本不传这个键。
 */
export function updateUser(
  userId: string,
  body: {
    is_active?: boolean
    role?: UserRole
    quota_tokens_daily?: number | null
    quota_concurrent_runs?: number | null
    dept?: string
  },
): Promise<AdminUser> {
  return request(`/api/admin/users/${userId}`, { method: 'PATCH', json: body })
}

export function systemStatus(): Promise<SystemStatus> {
  return request('/api/admin/system')
}
