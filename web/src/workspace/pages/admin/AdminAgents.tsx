import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AUTH_QUERY_KEY, me } from '../../../api/auth'
import { decideReview, listReviews, reviewKeys, setReviewCatalogEnabled } from '../../../api/reviews'
import { agentKeys } from '../../../api/agents'
import { errorMessage } from '../../../api/request'
import type { ReviewItem } from '../../../api/types'
import { Button } from '../../../components/ui/Button'
import { ADMIN_LIST_PAGE_SIZE, ADMIN_REVIEW_CARD_PAGE_SIZE, paginateAdminItems } from './AdminPaging'
import {
  AdminEmptyState,
  AdminListingDialog,
  AdminPageHeader,
  AdminPagination,
  AdminTableLoading,
  AdminTableSection,
  AdminViewTabs,
} from './AdminUi'
import { AgentReviewDetailDialog, reviewStatusClass, reviewStatusLabel } from './AdminReviewDetails'

/**
 * 智能体审核队列。
 *
 * **审的是版本不是 agent**：作者改一版就要重审一版，因此同一个 agent 会在这里
 * 出现多次，每次带着不同的版本号与那一版的提示词全文。
 *
 * **`reviewer` 也进得来。** 它只有这一页，账号与配额一样都碰不到。
 */
export function AdminAgents() {
  const queryClient = useQueryClient()
  const [view, setView] = useState<'pending' | 'decided'>('pending')
  const [pendingPage, setPendingPage] = useState(1)
  const [decidedPage, setDecidedPage] = useState(1)
  const [reasons, setReasons] = useState<Record<string, string>>({})
  const [failed, setFailed] = useState<Record<string, string>>({})
  const [detail, setDetail] = useState<ReviewItem | null>(null)
  const [listingTarget, setListingTarget] = useState<{ item: ReviewItem; enable: boolean } | null>(null)

  const reviews = useQuery({ queryKey: reviewKeys.list('agent'), queryFn: () => listReviews('agent') })
  const current = useQuery({ queryKey: AUTH_QUERY_KEY, queryFn: () => me() })
  const canOperate = current.data?.role === 'admin'
  const decide = useMutation({
    mutationFn: ({ id, approved, reason }: { id: string; approved: boolean; reason?: string }) =>
      decideReview(id, approved, reason),
    async onSuccess() {
      setPendingPage(1)
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: reviewKeys.all }),
        queryClient.invalidateQueries({ queryKey: agentKeys.all }),
      ])
    },
    onError(error, variables) {
      setFailed(current => ({ ...current, [variables.id]: errorMessage(error) }))
    },
  })
  const listing = useMutation({
    mutationFn: ({ id, enabled, reason }: { id: string; enabled: boolean; reason?: string }) => setReviewCatalogEnabled(id, enabled, reason),
    async onSuccess() {
      setListingTarget(null)
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: reviewKeys.all }),
        queryClient.invalidateQueries({ queryKey: agentKeys.all }),
      ])
    },
  })

  const pending = (reviews.data ?? []).filter(one => one.status === 'pending')
  const decided = (reviews.data ?? []).filter(one => one.status !== 'pending')
  const pendingResult = paginateAdminItems(pending, pendingPage, ADMIN_REVIEW_CARD_PAGE_SIZE)
  const decidedResult = paginateAdminItems(decided, decidedPage, ADMIN_LIST_PAGE_SIZE)

  const reject = (item: ReviewItem) => {
    const reason = (reasons[item.id] ?? '').trim()
    if (!reason) {
      // 后端也校验这一条 —— 这里拦住只是为了不让人白点一次
      setFailed(current => ({ ...current, [item.id]: '拒绝必须写明理由，作者要照着它改' }))
      return
    }
    setFailed(current => ({ ...current, [item.id]: '' }))
    decide.mutate({ id: item.id, approved: false, reason })
  }

  return (
    <div className="admin-page">
      <AdminPageHeader
        eyebrow="REVIEW · AGENTS"
        title="场景与智能体审核"
        description="通过的那一版出现在广场上。被拒的版本作者与组员照常可用 —— 审核管的是别人能不能看见。"
        pendingCount={pending.length}
      />

      {reviews.isError && <div role="alert" className="admin-alert">{errorMessage(reviews.error)}</div>}

      <AdminViewTabs
        label="切换审核记录"
        value={view}
        options={[
          { value: 'pending', label: '待审核', count: pending.length },
          { value: 'decided', label: '最近处理', count: decided.length },
        ]}
        onChange={setView}
      />

      {view === 'pending' ? (
        <AdminTableSection title={`待审核（${pending.length}）`}>
          {reviews.isPending && <AdminTableLoading label="正在加载审核队列…" />}
          {pending.length === 0 && !reviews.isPending && (
            <AdminEmptyState title="待审队列已清空" description="新的场景或智能体版本提审后会出现在这里。" />
          )}
          {pending.length > 0 && (
            <>
              <div className="admin-review-list">
                {pendingResult.items.map(item => (
                  <article key={item.id} data-testid="review-row" className="admin-review-card">
                    <Header item={item} />
                    <p className="admin-review-summary">{item.description || '未填写说明'}</p>
                    <div className="admin-review-actions">
                      <Button variant="secondary" size="sm" onClick={() => setDetail(item)}>查看详情</Button>
                      <input
                        value={reasons[item.id] ?? ''}
                        onChange={event => setReasons(current => ({ ...current, [item.id]: event.target.value }))}
                        placeholder="拒绝理由（拒绝时必填）"
                        aria-label={`${item.agent_name} 的拒绝理由`}
                        className="admin-reason-input"
                      />
                      <Button variant="secondary" size="sm" className="admin-danger-action" onClick={() => reject(item)} disabled={decide.isPending}>拒绝</Button>
                      <Button variant="primary" size="sm" onClick={() => decide.mutate({ id: item.id, approved: true })} disabled={decide.isPending}>通过</Button>
                    </div>
                    {failed[item.id] && <div role="alert" className="admin-row-alert">{failed[item.id]}</div>}
                  </article>
                ))}
              </div>
              <AdminPagination page={pendingResult.page} pageSize={ADMIN_REVIEW_CARD_PAGE_SIZE} totalItems={pending.length} itemName="待审记录" onPageChange={setPendingPage} />
            </>
          )}
        </AdminTableSection>
      ) : (
        <AdminTableSection title={`最近处理（${decided.length}）`}>
          {reviews.isPending ? <AdminTableLoading label="正在加载处理记录…" /> : decided.length === 0 ? <AdminEmptyState title="还没有处理记录" /> : (
            <>
              <div className="admin-review-list compact">
                {decidedResult.items.map(item => (
                  <article key={item.id} data-testid="review-row" className="admin-review-card compact">
                    <Header item={item} />
                    {item.reason && <div className="admin-row-alert">拒绝理由：{item.reason}</div>}
                    {item.catalog_disabled_reason && <div className="admin-row-alert">下架原因：{item.catalog_disabled_reason}</div>}
                    {item.status === 'approved' && (
                      <div className="admin-review-compact-actions">
                        <Button variant="secondary" size="sm" onClick={() => setDetail(item)}>查看详情</Button>
                        {canOperate && (
                          <Button
                            variant={item.catalog_enabled ? 'secondary' : 'primary'}
                            size="sm"
                            className={item.catalog_enabled ? 'admin-danger-action' : ''}
                            onClick={() => setListingTarget({ item, enable: !item.catalog_enabled })}
                          >
                            {item.catalog_enabled ? '下架' : '恢复上架'}
                          </Button>
                        )}
                      </div>
                    )}
                  </article>
                ))}
              </div>
              <AdminPagination page={decidedResult.page} pageSize={ADMIN_LIST_PAGE_SIZE} totalItems={decided.length} itemName="处理记录" onPageChange={setDecidedPage} />
            </>
          )}
        </AdminTableSection>
      )}
      <AgentReviewDetailDialog item={detail} onClose={() => setDetail(null)} />
      <AdminListingDialog
        open={listingTarget !== null}
        resourceName={listingTarget?.item.agent_name ?? '该内容'}
        enable={listingTarget?.enable ?? false}
        pending={listing.isPending}
        error={listing.isError ? errorMessage(listing.error) : undefined}
        onConfirm={reason => {
          if (listingTarget) listing.mutate({ id: listingTarget.item.id, enabled: listingTarget.enable, reason })
        }}
        onClose={() => setListingTarget(null)}
      />
    </div>
  )
}

function Header({ item }: { item: ReviewItem }) {
  const scenario = (item.subagent_refs?.length ?? 0) > 0
  return (
    <div className="admin-review-header">
      <span className="admin-review-title">{item.agent_name}</span>
      <span className="admin-review-version">v{item.version}</span>
      <span className="admin-tag">{scenario ? '场景' : '智能体'}</span>
      <span className="admin-review-meta">{item.owner_name} · {item.subject || '未分类'}</span>
      <span className={`admin-review-status ${reviewStatusClass(item)}`}>{reviewStatusLabel(item)}</span>
      {!item.responsibility_confirmed && <span className="admin-review-warning">未勾责任确认</span>}
    </div>
  )
}
