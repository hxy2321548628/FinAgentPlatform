import { request } from './request'
import type { Me, RegisterResponse } from './types'

export const AUTH_QUERY_KEY = ['auth', 'me'] as const

export function register(
  name: string,
  email: string,
  password: string,
  inviteCode = '',
  dept = '',
): Promise<RegisterResponse> {
  return request('/api/auth/register', {
    method: 'POST',
    json: { name, email, password, dept: dept.trim(), invite_code: inviteCode.trim() || undefined },
    redirectOn401: false,
  })
}

/** 登录。`name` 收用户名**或**邮箱 —— 后端两者都认，字段名沿用旧的以免打穿调用方。 */
export function login(name: string, password: string): Promise<Me> {
  return request('/api/auth/login', {
    method: 'POST',
    json: { name, password },
    redirectOn401: false,
  })
}

export function me(options: { redirectOn401?: boolean } = {}): Promise<Me> {
  return request('/api/auth/me', { redirectOn401: options.redirectOn401 })
}

export function logout(): Promise<void> {
  return request('/api/auth/logout', { method: 'POST' })
}
