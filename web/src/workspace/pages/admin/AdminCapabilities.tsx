import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AUTH_QUERY_KEY, me } from '../../../api/auth'
import { decideApplication, listForAdmin, mcpKeys, probe, setEnabled } from '../../../api/mcp'
import { decideReview, listReviews, reviewKeys } from '../../../api/reviews'
import { errorMessage } from '../../../api/request'
import { skillKeys } from '../../../api/skills'
import type { AdminMcpServer, McpProbe, ReviewItem } from '../../../api/types'
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
                    style={{ width: 180, padding: '6px 8px', border: '1px solid var(--border)', borderRadius: 6, fontSize: 12, fontFamily: 'inherit', background: '#F7F9FC' }}
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

/**
 * MCP 管理。**只有管理员进得来** —— reviewer 审的是内容合规，放行一个外网地址是
 * 安全边界决定。声明有写操作的一律批不了，那是后端的硬闸门，这里只把理由显示出来。
 */
export function AdminMcp() {
  const queryClient = useQueryClient()
  const servers = useQuery({ queryKey: mcpKeys.admin(), queryFn: listForAdmin })
  // **审核员批得了但停不了、探不了**：那两个是运维动作，后端也回 403。
  // 摆一个必然失败的按钮比不摆更糟 —— 点下去只会得到一句「需要管理员权限」
  const current = useQuery({ queryKey: AUTH_QUERY_KEY, queryFn: () => me() })
  const canOperate = current.data?.role === 'admin'
  const [reasons, setReasons] = useState<Record<string, string>>({})
  const [failed, setFailed] = useState<Record<string, string>>({})
  const [probes, setProbes] = useState<Record<string, McpProbe>>({})

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: mcpKeys.all })
  }
  const remember = (id: string, error: unknown) => {
    setFailed(current => ({ ...current, [id]: errorMessage(error) }))
  }

  const decide = useMutation({
    mutationFn: ({ id, approved, reason }: { id: string; approved: boolean; reason?: string }) =>
      decideApplication(id, approved, reason),
    onSuccess: refresh,
    onError: (error, variables) => remember(variables.id, error),
  })
  const toggle = useMutation({
    mutationFn: ({ id, enabled, reason }: { id: string; enabled: boolean; reason?: string }) =>
      setEnabled(id, enabled, reason),
    onSuccess: refresh,
    onError: (error, variables) => remember(variables.id, error),
  })
  const test = useMutation({
    mutationFn: (id: string) => probe(id),
    onSuccess: async (result, id) => {
      setProbes(current => ({ ...current, [id]: result }))
      await refresh()
    },
    onError: (error, id) => remember(id, error),
  })

  const items = servers.data ?? []
  const pending = items.filter(one => one.status === 'pending')
  const live = items.filter(one => one.status === 'enabled' || one.status === 'disabled')
  const closed = items.filter(one => one.status === 'rejected')

  const reject = (item: AdminMcpServer) => {
    const reason = (reasons[item.id] ?? '').trim()
    if (!reason) {
      setFailed(current => ({ ...current, [item.id]: '拒绝必须写明理由，申请人要照着它改' }))
      return
    }
    setFailed(current => ({ ...current, [item.id]: '' }))
    decide.mutate({ id: item.id, approved: false, reason })
  }

  return (
    <div style={pageStyle}>
      <AdminPageHeader eyebrow="// MCP MANAGEMENT" title="MCP 管理" pendingCount={pending.length} />
      {servers.isPending && <div style={{ color: 'var(--text-muted)' }}>正在加载 MCP 目录…</div>}
      {servers.isError && <div role="alert" style={{ color: '#DC2626' }}>{errorMessage(servers.error)}</div>}

      <AdminTableSection title={`待审核 MCP Servers（${pending.length}）`}>
        {pending.length === 0 && !servers.isPending ? <div style={emptyStyle}>队列是空的</div> : (
          <McpTable
            records={pending}
            probes={probes}
            failed={failed}
            action={item => (
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                <input
                  value={reasons[item.id] ?? ''}
                  onChange={event => setReasons(current => ({ ...current, [item.id]: event.target.value }))}
                  placeholder="拒绝理由（拒绝时必填）"
                  aria-label={`${item.name} 的拒绝理由`}
                  style={reasonInputStyle}
                />
                <button type="button" onClick={() => reject(item)} disabled={decide.isPending} style={rejectButtonStyle}>拒绝</button>
                <button type="button" onClick={() => decide.mutate({ id: item.id, approved: true })} disabled={decide.isPending} style={approveButtonStyle}>通过</button>
              </div>
            )}
          />
        )}
      </AdminTableSection>

      <AdminTableSection title={`已放行 MCP Servers（${live.length}）`}>
        {live.length === 0 ? <div style={emptyStyle}>还没有放行任何 MCP</div> : (
          <McpTable
            records={live}
            probes={probes}
            failed={failed}
            action={item => !canOperate ? null : (
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                <button type="button" onClick={() => test.mutate(item.id)} disabled={test.isPending} style={secondaryButtonStyle}>测试连接</button>
                {item.status === 'enabled'
                  ? <button type="button" onClick={() => toggle.mutate({ id: item.id, enabled: false, reason: '管理员手动停用' })} disabled={toggle.isPending} style={rejectButtonStyle}>停用</button>
                  : <button type="button" onClick={() => toggle.mutate({ id: item.id, enabled: true })} disabled={toggle.isPending} style={approveButtonStyle}>恢复</button>}
              </div>
            )}
          />
        )}
      </AdminTableSection>

      {closed.length > 0 && (
        <AdminTableSection title={`已拒绝（${closed.length}）`}>
          <McpTable records={closed} probes={probes} failed={failed} action={item => <span style={{ color: '#DC2626' }}>{item.disabled_reason}</span>} />
        </AdminTableSection>
      )}
    </div>
  )
}

/**
 * 自动停用与手动停用要分得开。
 *
 * **管理员总是最后一个知道**是 F5 修订版接受的代价：飞书通道随可观测性一起撤了，
 * 剩下的降级手段只有日志与这一格标记。它必须一眼看得出「不是我停的」。
 */
function statusLabel(item: AdminMcpServer): string {
  if (item.status === 'pending') return '待审核'
  if (item.status === 'rejected') return '已拒绝'
  if (item.status === 'enabled') return '已上架'
  return item.disabled_reason?.includes('连续失败') ? '已自动停用' : '已停用'
}

function McpTable({ records, probes, failed, action }: {
  records: AdminMcpServer[]
  probes: Record<string, McpProbe>
  failed: Record<string, string>
  action: (record: AdminMcpServer) => React.ReactNode
}) {
  const headers = ['名称', '申请人', '地址', '四项声明', '状态', '操作']
  return (
    <table style={tableStyle}>
      <thead><tr>{headers.map(label => <th key={label} style={thStyle}>{label}</th>)}</tr></thead>
      <tbody>
        {records.map((record, index) => {
          const result = probes[record.id]
          return (
            <tr key={record.id} data-testid="mcp-row" style={{ borderBottom: index < records.length - 1 ? '1px solid var(--border-light)' : 'none' }}>
              <td style={nameCellStyle}>
                <div>{record.name}</div>
                <div style={{ marginTop: 3, color: 'var(--text-muted)', fontSize: 11, fontWeight: 400 }}>{record.description}</div>
              </td>
              <td style={cellStyle}>{record.submitter_name}</td>
              <td style={monoCellStyle}>{record.url}</td>
              <td style={cellStyle}>
                <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{record.tool_names.length} 个工具 · {record.latency_note || '未声明耗时'}</div>
                <div style={{ marginTop: 3, display: 'flex', gap: 5, flexWrap: 'wrap' }}>
                  {record.stores_user_data && <span style={tagStyle}>存储用户数据</span>}
                  {record.sends_data_out && <span style={tagStyle}>转发数据</span>}
                  {record.has_write_operation && <span style={{ ...tagStyle, color: '#DC2626' }}>有写操作 · 不可批</span>}
                </div>
              </td>
              <td style={cellStyle}>
                <div>{statusLabel(record)}</div>
                {record.disabled_reason && <div style={{ marginTop: 3, color: '#92400E', fontSize: 11 }}>{record.disabled_reason}</div>}
                {record.failure_count > 0 && <div style={{ marginTop: 3, color: '#92400E', fontSize: 11 }}>连续失败 {record.failure_count} 次</div>}
                {result && <div style={{ marginTop: 3, fontSize: 11, color: result.reachable ? '#059669' : '#DC2626' }}>
                  {result.reachable ? `连通，拿到 ${result.tool_names.length} 个工具` : '连不上'}
                  {result.undeclared.length > 0 && `；清单外多出：${result.undeclared.join('、')}`}
                  {result.declared_only.length > 0 && `；清单里有但实际没有：${result.declared_only.join('、')}`}
                </div>}
              </td>
              <td style={cellStyle}>
                {action(record)}
                {failed[record.id] && <div role="alert" style={{ marginTop: 8, color: '#DC2626', fontSize: 12 }}>{failed[record.id]}</div>}
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

const reasonInputStyle: React.CSSProperties = { width: 180, padding: '6px 8px', border: '1px solid var(--border)', borderRadius: 6, fontSize: 12, fontFamily: 'inherit', background: '#F7F9FC' }
