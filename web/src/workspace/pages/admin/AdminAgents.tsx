import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { decideReview, listReviews, reviewKeys } from '../../../api/reviews'
import { agentKeys } from '../../../api/agents'
import { errorMessage } from '../../../api/request'
import type { ReviewItem } from '../../../api/types'
import { emptyStyle, pageStyle, sectionStyle } from './AdminStyles'
import { AdminPageHeader } from './AdminUi'

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
  const [reasons, setReasons] = useState<Record<string, string>>({})
  const [failed, setFailed] = useState<Record<string, string>>({})

  const reviews = useQuery({ queryKey: reviewKeys.list('agent'), queryFn: () => listReviews('agent') })
  const decide = useMutation({
    mutationFn: ({ id, approved, reason }: { id: string; approved: boolean; reason?: string }) =>
      decideReview(id, approved, reason),
    async onSuccess() {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: reviewKeys.all }),
        queryClient.invalidateQueries({ queryKey: agentKeys.all }),
      ])
    },
    onError(error, variables) {
      setFailed(current => ({ ...current, [variables.id]: errorMessage(error) }))
    },
  })

  const pending = (reviews.data ?? []).filter(one => one.status === 'pending')
  const decided = (reviews.data ?? []).filter(one => one.status !== 'pending')

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
    <div style={pageStyle}>
      <AdminPageHeader
        eyebrow="// AGENT REVIEW"
        title="智能体审核"
        description="通过的那一版出现在广场上。被拒的版本作者与组员照常可用 —— 审核管的是别人能不能看见。"
        pendingCount={pending.length}
      />

      {reviews.isPending && <div style={{ color: 'var(--text-muted)' }}>正在加载审核队列…</div>}
      {reviews.isError && <div role="alert" style={{ color: 'var(--danger)' }}>{errorMessage(reviews.error)}</div>}

      <section style={{ ...sectionStyle, padding: '16px 18px' }}>
        <div style={sectionHeading}>待审核（{pending.length}）</div>
        {pending.length === 0 && !reviews.isPending && (
          <div style={emptyStyle}>队列是空的</div>
        )}
        {pending.map(item => (
          <article key={item.id} data-testid="review-row" style={rowStyle}>
            <Header item={item} />
            <Prompt text={item.system_prompt ?? ''} />
            <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start', marginTop: 12 }}>
              <input
                value={reasons[item.id] ?? ''}
                onChange={event => setReasons(current => ({ ...current, [item.id]: event.target.value }))}
                placeholder="拒绝理由（拒绝时必填）"
                aria-label={`${item.agent_name} 的拒绝理由`}
                style={{ flex: 1, padding: '7px 10px', border: '1px solid var(--border)', borderRadius: 6, fontSize: 12, fontFamily: 'inherit', background: 'var(--input-bg)' }}
              />
              <button onClick={() => reject(item)} disabled={decide.isPending} style={{ padding: '7px 14px', background: 'transparent', color: 'var(--danger)', border: '1px solid #FECACA', borderRadius: 6, fontSize: 12, cursor: 'pointer', fontFamily: 'inherit' }}>拒绝</button>
              <button onClick={() => decide.mutate({ id: item.id, approved: true })} disabled={decide.isPending} style={{ padding: '7px 16px', background: 'var(--action)', color: '#fff', border: 'none', borderRadius: 6, fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>通过</button>
            </div>
            {failed[item.id] && <div role="alert" style={{ marginTop: 8, color: 'var(--danger)', fontSize: 12 }}>{failed[item.id]}</div>}
          </article>
        ))}
      </section>

      <section style={{ ...sectionStyle, padding: '16px 18px' }}>
        <div style={sectionHeading}>最近处理（{decided.length}）</div>
        {decided.length === 0 && <div style={emptyStyle}>还没有处理过任何提审</div>}
        {decided.map(item => (
          <article key={item.id} data-testid="review-row" style={rowStyle}>
            <Header item={item} />
            {item.reason && <div style={{ marginTop: 6, fontSize: 12, color: 'var(--danger)' }}>拒绝理由：{item.reason}</div>}
          </article>
        ))}
      </section>
    </div>
  )
}

function Header({ item }: { item: ReviewItem }) {
  const label = { pending: '待审核', approved: '已通过', rejected: '已拒绝' }[item.status]
  const tone = { pending: 'var(--status-warn)', approved: 'var(--status-done)', rejected: 'var(--danger)' }[item.status]
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
      <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>{item.agent_name}</span>
      <span style={{ fontSize: 11, fontFamily: "'JetBrains Mono', monospace", color: 'var(--text-muted)' }}>v{item.version}</span>
      <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{item.owner_name} · {item.subject || '未分类'}</span>
      <span style={{ padding: '1px 8px', borderRadius: 10, fontSize: 11, fontWeight: 600, color: tone, border: `1px solid ${tone}` }}>{label}</span>
      {!item.responsibility_confirmed && <span style={{ fontSize: 11, color: 'var(--danger)' }}>未勾责任确认</span>}
    </div>
  )
}

function Prompt({ text }: { text: string }) {
  return (
    <div style={{ marginTop: 10 }}>
      <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>系统提示词全文</div>
      <div style={{ maxHeight: 220, overflowY: 'auto', background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 6, padding: '10px 12px', fontSize: 12, fontFamily: "'JetBrains Mono', monospace", color: 'var(--text-secondary)', lineHeight: 1.75, whiteSpace: 'pre-wrap' }}>
        {text}
      </div>
    </div>
  )
}

const sectionHeading: React.CSSProperties = {
  fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', padding: '0 0 12px',
}

const rowStyle: React.CSSProperties = {
  padding: '14px 0', borderTop: '1px solid var(--border-light)',
}
