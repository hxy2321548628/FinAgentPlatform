import { request } from './request'
import type { Me } from './types'

export const AUTH_QUERY_KEY = ['auth', 'me'] as const

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
