import { describe, expect, it } from 'vitest'
import { ApiError, type ErrorCode } from './api/request'
import { queryClient } from './queryClient'

const retry = queryClient.getDefaultOptions().queries?.retry as (failureCount: number, error: unknown) => boolean

function apiError(status: number, code: ErrorCode) {
  return new ApiError(status, code, '')
}

describe('查询重试策略', () => {
  // 限流下重试是在给闸门续命：被拒的请求自己又发了两次，一次误触发变成三倍流量，
  // 而窗口是滑动的 —— 放大之后它反而更难清空。这一条就该让用户看见「慢一点」。
  it('撞上频率限制时不重试', () => {
    expect(retry(0, apiError(429, 'RATE_LIMITED'))).toBe(false)
  })

  it('配额与并发上限同样不重试 —— 重试改变不了结果', () => {
    expect(retry(0, apiError(429, 'QUOTA_EXCEEDED'))).toBe(false)
    expect(retry(0, apiError(429, 'CONCURRENCY_LIMIT'))).toBe(false)
  })

  it('服务端错误与断网仍然重试', () => {
    expect(retry(0, apiError(503, 'INTERNAL'))).toBe(true)
    expect(retry(0, apiError(0, 'INTERNAL'))).toBe(true)
  })

  it('客户端错误不重试', () => {
    expect(retry(0, apiError(404, 'NOT_FOUND'))).toBe(false)
    expect(retry(0, apiError(422, 'VALIDATION_ERROR'))).toBe(false)
  })

  it('重试次数封顶', () => {
    expect(retry(2, apiError(503, 'INTERNAL'))).toBe(false)
  })
})
