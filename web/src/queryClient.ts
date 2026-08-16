import { QueryClient } from '@tanstack/react-query'
import { ApiError } from './api/request'

// **429 一律不重试**，三个 code 都不。限流那一条尤其反直觉：重试等于给闸门续命 ——
// 一次误触发被放大成三倍流量，而窗口是滑动的，放大之后它反而更难清空。
// 这时该让教师看见「操作太快了」并自己停手，那正是这道闸想要的效果。
function shouldRetry(failureCount: number, error: unknown): boolean {
  if (failureCount >= 2) return false
  if (!(error instanceof ApiError)) return failureCount < 1
  return error.status === 0 || error.status >= 500
}

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 15_000,
      retry: shouldRetry,
      refetchOnWindowFocus: false,
    },
    mutations: {
      retry: false,
    },
  },
})
