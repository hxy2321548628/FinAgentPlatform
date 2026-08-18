import { request } from './request'
import type { ReviewItem, SkillFileContent, SkillFileEntry } from './types'

export const reviewKeys = {
  all: ['reviews'] as const,
  list: (targetKind?: 'agent' | 'skill') => ['reviews', 'list', targetKind ?? 'all'] as const,
}

/** 审核队列：待审的在前，后面跟着最近处理过的那些。只有 reviewer 与 admin 打得开。 */
export function listReviews(targetKind?: 'agent' | 'skill'): Promise<ReviewItem[]> {
  return request<ReviewItem[]>('/api/reviews').then(items => targetKind ? items.filter(one => one.target_kind === targetKind) : items)
}

/** 按审核标识读取冻结版本的完整详情。 */
export function getReview(reviewId: string): Promise<ReviewItem> {
  return request(`/api/reviews/${encodeURIComponent(reviewId)}`)
}

/** 列出被审 Skill 版本的文件。 */
export function listReviewSkillFiles(reviewId: string): Promise<SkillFileEntry[]> {
  return request(`/api/reviews/${encodeURIComponent(reviewId)}/files`)
}

/** 读取被审 Skill 版本的一个文件。 */
export function readReviewSkillFile(reviewId: string, path: string): Promise<SkillFileContent> {
  const params = new URLSearchParams({ path })
  return request(`/api/reviews/${encodeURIComponent(reviewId)}/files/content?${params}`)
}

/** 通过或拒绝。**拒绝必须带理由**，后端也校验。 */
export function decideReview(reviewId: string, approved: boolean, reason?: string): Promise<ReviewItem> {
  return request(`/api/reviews/${encodeURIComponent(reviewId)}`, {
    method: 'POST',
    json: { approved, reason: reason ?? null },
  })
}

/** 管理员上架或下架一个已过审的 Agent、场景或 Skill。 */
export function setReviewCatalogEnabled(
  reviewId: string,
  enabled: boolean,
  reason?: string,
): Promise<ReviewItem> {
  return request(`/api/reviews/${encodeURIComponent(reviewId)}/catalog`, {
    method: 'POST',
    json: { enabled, reason: reason ?? null },
  })
}
