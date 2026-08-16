import { request } from './request'
import type { Usage, UsageRanking } from './types'

export const usageKeys = {
  mine: () => ['usage', 'me'] as const,
  ranking: () => ['usage', 'ranking'] as const,
}

export function myUsage(): Promise<Usage> {
  return request('/api/usage/me')
}

export function usageRanking(): Promise<UsageRanking> {
  return request('/api/usage/ranking')
}
