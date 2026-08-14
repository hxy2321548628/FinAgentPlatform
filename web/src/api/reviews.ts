import { request } from './request'
import type { ReviewItem } from './types'

export const reviewKeys = {
  all: ['reviews'] as const,
  list: () => ['reviews', 'list'] as const,
}

/** 审核队列：待审的在前，后面跟着最近处理过的那些。只有 reviewer 与 admin 打得开。 */
export function listReviews(): Promise<ReviewItem[]> {
  return request('/api/reviews')
}

/** 通过或拒绝。**拒绝必须带理由**，后端也校验。 */
export function decideReview(reviewId: string, approved: boolean, reason?: string): Promise<ReviewItem> {
  return request(`/api/reviews/${encodeURIComponent(reviewId)}`, {
    method: 'POST',
    json: { approved, reason: reason ?? null },
  })
}
