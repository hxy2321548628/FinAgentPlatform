import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { decideReview, listReviews, reviewKeys } from '../../../api/reviews'
import { errorMessage } from '../../../api/request'
import { skillKeys } from '../../../api/skills'
import type { ReviewItem } from '../../../api/types'
import { AdminPageHeader, AdminTableSection } from './AdminUi'
import {
  approveButtonStyle,
  cellStyle,
  emptyStyle,
  monoCellStyle,
  nameCellStyle,
  pageStyle,
  rejectButtonStyle,
  secondaryButtonStyle,
  tableStyle,
  tagStyle,
  thStyle,
} from './AdminStyles'

interface CapabilityRecord {
  id: string
  name: string
  owner: string
  category: string
  summary: string
  specification: string
  submittedAt?: string
  publishedAt?: string
  calls?: number
}

const PENDING_MCP: CapabilityRecord[] = [
  { id: 'mcp-p1', name: '校内数据库查询', owner: '实验中心', category: '业务系统', summary: '为获批场景提供校内研究数据库的只读查询能力。', specification: 'Tools 3 · Resources 2 · Prompts 0', submittedAt: '2026-08-11 10:25' },
]

const PUBLISHED_MCP: CapabilityRecord[] = [
  { id: 'mcp-s1', name: '财报检索服务', owner: '金融学院', category: '金融数据', summary: '检索上市公司定期报告并返回文档与元数据。', specification: 'Tools 2 · Resources 1 · Prompts 1', publishedAt: '2026-07-08', calls: 95 },
  { id: 'mcp-s2', name: '论文检索服务', owner: '图书馆', category: '学术资源', summary: '按主题、作者与年份检索学术论文元数据。', specification: 'Tools 2 · Resources 2 · Prompts 0', publishedAt: '2026-07-18', calls: 73 },
]

/** Skill 版本审核队列。reviewer 与 admin 均可进入。 */
export function AdminSkills() {
  const queryClient = useQueryClient()
  const [reasons, setReasons] = useState<Record<string, string>>({})
  const [failed, setFailed] = useState<Record<string, string>>({})
  const reviews = useQuery({ queryKey: reviewKeys.list('skill'), queryFn: () => listReviews('skill') })
  const decide = useMutation({
    mutationFn: ({ id, approved, reason }: { id: string; approved: boolean; reason?: string }) =>
      decideReview(id, approved, reason),
    async onSuccess() {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: reviewKeys.all }),
        queryClient.invalidateQueries({ queryKey: skillKeys.all }),
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
      setFailed(current => ({ ...current, [item.id]: '拒绝必须写明理由，作者要照着它改' }))
      return
    }
    setFailed(current => ({ ...current, [item.id]: '' }))
    decide.mutate({ id: item.id, approved: false, reason })
  }

  return (
    <div style={pageStyle}>
      <AdminPageHeader eyebrow="// SKILL MANAGEMENT" title="Skill 审核" pendingCount={pending.length} />

      {reviews.isPending && <div style={{ color: 'var(--text-muted)' }}>正在加载审核队列…</div>}
      {reviews.isError && <div role="alert" style={{ color: '#DC2626' }}>{errorMessage(reviews.error)}</div>}

      <AdminTableSection title={`待审核 Skills（${pending.length}）`}>
        {pending.length === 0 && !reviews.isPending ? <div style={emptyStyle}>队列是空的</div> : (
          <SkillReviewTable
            records={pending}
            action={item => (
              <>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <input
                    value={reasons[item.id] ?? ''}
                    onChange={event => setReasons(current => ({ ...current, [item.id]: event.target.value }))}
                    placeholder="拒绝理由（拒绝时必填）"
                    aria-label={`${item.skill_name ?? '未命名 Skill'} 的拒绝理由`}
                    style={{ width: 180, padding: '6px 8px', border: '1px solid var(--border)', borderRadius: 6, fontSize: 12, fontFamily: 'inherit', outline: 'none', background: '#F7F9FC' }}
                  />
                  <button type="button" onClick={() => reject(item)} disabled={decide.isPending} style={rejectButtonStyle}>拒绝</button>
                  <button type="button" onClick={() => decide.mutate({ id: item.id, approved: true })} disabled={decide.isPending} style={approveButtonStyle}>通过</button>
                </div>
                {failed[item.id] && <div role="alert" style={{ marginTop: 8, color: '#DC2626', fontSize: 12 }}>{failed[item.id]}</div>}
              </>
            )}
          />
        )}
      </AdminTableSection>

      <AdminTableSection title={`最近处理（${decided.length}）`}>
        {decided.length === 0 ? <div style={emptyStyle}>还没有处理过任何提审</div> : (
          <SkillReviewTable records={decided} action={item => item.reason ? <span style={{ color: '#DC2626' }}>拒绝理由：{item.reason}</span> : null} />
        )}
      </AdminTableSection>
    </div>
  )
}

function SkillReviewTable({ records, action }: { records: ReviewItem[]; action: (item: ReviewItem) => React.ReactNode }) {
  return (
    <table style={tableStyle}>
      <thead><tr>{['名称', '提交方', '分类', '版本内容', '状态', '操作'].map(label => <th key={label} style={thStyle}>{label}</th>)}</tr></thead>
      <tbody>
        {records.map((item, index) => (
          <tr key={item.id} data-testid="review-row" style={{ borderBottom: index < records.length - 1 ? '1px solid var(--border-light)' : 'none' }}>
            <td style={nameCellStyle}>
              <div>{item.skill_name ?? '未命名 Skill'} <span style={{ color: 'var(--text-muted)', fontWeight: 400 }}>v{item.version}</span></div>
              <div style={{ marginTop: 3, color: 'var(--text-muted)', fontSize: 11, fontWeight: 400 }}>{item.description}</div>
            </td>
            <td style={cellStyle}>{item.owner_name}</td>
            <td style={cellStyle}><span style={tagStyle}>{item.subject || '未分类'}</span></td>
            <td style={monoCellStyle}>{item.file_count ?? 0} 个文件 · {formatBytes(item.total_bytes ?? 0)}</td>
            <td style={cellStyle}>{reviewStatus(item.status)}{!item.responsibility_confirmed && <div style={{ color: '#DC2626', fontSize: 11 }}>未勾责任确认</div>}</td>
            <td style={cellStyle}>{action(item)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function reviewStatus(status: ReviewItem['status']): string {
  return { pending: '待审核', approved: '已通过', rejected: '已拒绝' }[status]
}

function formatBytes(bytes: number): string {
  return bytes < 1024 ? `${bytes} B` : `${(bytes / 1024).toFixed(1)} KB`
}

export function AdminMcp() {
  const [pending, setPending] = useState(PENDING_MCP)
  const [published, setPublished] = useState(PUBLISHED_MCP)

  const approve = (record: CapabilityRecord) => {
    setPending(current => current.filter(item => item.id !== record.id))
    setPublished(current => [{ ...record, publishedAt: '刚刚', calls: 0 }, ...current])
  }

  return (
    <div style={pageStyle}>
      <AdminPageHeader eyebrow="// MCP MANAGEMENT" title="MCP 管理" pendingCount={pending.length} />
      <McpTable
        title="待审核 MCP Servers"
        records={pending}
        action={record => (
          <div style={{ display: 'flex', gap: 8 }}>
            <button type="button" onClick={() => approve(record)} style={approveButtonStyle}>通过</button>
            <button type="button" onClick={() => setPending(current => current.filter(item => item.id !== record.id))} style={rejectButtonStyle}>拒绝</button>
          </div>
        )}
      />
      <McpTable
        title="已放行 MCP Servers"
        records={published}
        published
        action={record => <button type="button" onClick={() => setPublished(current => current.filter(item => item.id !== record.id))} style={secondaryButtonStyle}>下架</button>}
      />
    </div>
  )
}

function McpTable({ title, records, published = false, action }: { title: string; records: CapabilityRecord[]; published?: boolean; action: (record: CapabilityRecord) => React.ReactNode }) {
  const headers = ['名称', '提交方', '分类', '协议能力', published ? '上架时间' : '提交时间', published ? '调用量' : '说明', '操作']
  return (
    <AdminTableSection title={title}>
      {records.length === 0 ? <div style={emptyStyle}>暂无记录</div> : (
        <table style={tableStyle}>
          <thead><tr>{headers.map(label => <th key={label} style={thStyle}>{label}</th>)}</tr></thead>
          <tbody>
            {records.map((record, index) => (
              <tr key={record.id} style={{ borderBottom: index < records.length - 1 ? '1px solid var(--border-light)' : 'none' }}>
                <td style={nameCellStyle}><div>{record.name}</div><div style={{ marginTop: 3, color: 'var(--text-muted)', fontSize: 11, fontWeight: 400 }}>{record.summary}</div></td>
                <td style={cellStyle}>{record.owner}</td>
                <td style={cellStyle}><span style={tagStyle}>{record.category}</span></td>
                <td style={monoCellStyle}>{record.specification}</td>
                <td style={monoCellStyle}>{published ? record.publishedAt : record.submittedAt}</td>
                <td style={cellStyle}>{published ? `${record.calls ?? 0} 次` : '内容与安全检查'}</td>
                <td style={cellStyle}>{action(record)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </AdminTableSection>
  )
}
