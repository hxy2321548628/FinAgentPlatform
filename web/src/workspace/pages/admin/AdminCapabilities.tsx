import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AUTH_QUERY_KEY, me } from '../../../api/auth'
import { decideApplication, listForAdmin, mcpKeys, probe, setEnabled } from '../../../api/mcp'
import { decideReview, listReviews, reviewKeys, setReviewCatalogEnabled } from '../../../api/reviews'
import { errorMessage } from '../../../api/request'
import { skillKeys } from '../../../api/skills'
import type { AdminMcpServer, McpProbe, ReviewItem } from '../../../api/types'
import { Button } from '../../../components/ui/Button'
import { ADMIN_ACTION_PAGE_SIZE, ADMIN_DETAIL_PAGE_SIZE, paginateAdminItems } from './AdminPaging'
import {
  AdminEmptyState,
  AdminListingDialog,
  AdminPageHeader,
  AdminPagination,
  AdminTableLoading,
  AdminTableSection,
  AdminViewTabs,
} from './AdminUi'
import { McpDetailDialog, SkillReviewDetailDialog, reviewStatusLabel } from './AdminReviewDetails'

/** Skill 版本审核队列。reviewer 与 admin 均可进入。 */
export function AdminSkills() {
  const queryClient = useQueryClient()
  const [view, setView] = useState<'pending' | 'decided'>('pending')
  const [pendingPage, setPendingPage] = useState(1)
  const [decidedPage, setDecidedPage] = useState(1)
  const [reasons, setReasons] = useState<Record<string, string>>({})
  const [failed, setFailed] = useState<Record<string, string>>({})
  const [detail, setDetail] = useState<ReviewItem | null>(null)
  const [listingTarget, setListingTarget] = useState<{ item: ReviewItem; enable: boolean } | null>(null)
  const reviews = useQuery({ queryKey: reviewKeys.list('skill'), queryFn: () => listReviews('skill') })
  const current = useQuery({ queryKey: AUTH_QUERY_KEY, queryFn: () => me() })
  const canOperate = current.data?.role === 'admin'
  const decide = useMutation({
    mutationFn: ({ id, approved, reason }: { id: string; approved: boolean; reason?: string }) =>
      decideReview(id, approved, reason),
    async onSuccess() {
      setPendingPage(1)
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: reviewKeys.all }),
        queryClient.invalidateQueries({ queryKey: skillKeys.all }),
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
        queryClient.invalidateQueries({ queryKey: skillKeys.all }),
      ])
    },
  })

  const pending = (reviews.data ?? []).filter(one => one.status === 'pending')
  const decided = (reviews.data ?? []).filter(one => one.status !== 'pending')
  const pendingResult = paginateAdminItems(pending, pendingPage, ADMIN_ACTION_PAGE_SIZE)
  const decidedResult = paginateAdminItems(decided, decidedPage, ADMIN_DETAIL_PAGE_SIZE)

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
    <div className="admin-page">
      <AdminPageHeader eyebrow="REVIEW · SKILLS" title="Skill 审核" description="审查共享 Skill 的说明、分类与版本文件，通过后才会向全平台开放。" pendingCount={pending.length} />

      {reviews.isError && <div role="alert" className="admin-alert">{errorMessage(reviews.error)}</div>}

      <AdminViewTabs
        label="切换 Skill 审核记录"
        value={view}
        options={[
          { value: 'pending', label: '待审核', count: pending.length },
          { value: 'decided', label: '最近处理', count: decided.length },
        ]}
        onChange={setView}
      />

      {view === 'pending' ? (
        <AdminTableSection title={`待审核 Skills（${pending.length}）`}>
          {reviews.isPending ? <AdminTableLoading label="正在加载 Skill 审核队列…" /> : pending.length === 0 ? <AdminEmptyState title="待审队列已清空" /> : (
            <>
              <SkillReviewTable
                records={pendingResult.items}
                stickyActions
                action={item => (
                  <>
                    <div className="admin-review-table-actions admin-review-table-actions--with-detail">
                      <input
                        value={reasons[item.id] ?? ''}
                        onChange={event => setReasons(current => ({ ...current, [item.id]: event.target.value }))}
                        placeholder="拒绝理由（拒绝时必填）"
                        aria-label={`${item.skill_name ?? '未命名 Skill'} 的拒绝理由`}
                        className="admin-reason-input"
                      />
                      <Button variant="secondary" size="sm" onClick={() => setDetail(item)}>查看</Button>
                      <Button variant="secondary" size="sm" className="admin-danger-action" onClick={() => reject(item)} disabled={decide.isPending}>拒绝</Button>
                      <Button variant="primary" size="sm" onClick={() => decide.mutate({ id: item.id, approved: true })} disabled={decide.isPending}>通过</Button>
                    </div>
                    {failed[item.id] && <div role="alert" className="admin-row-alert">{failed[item.id]}</div>}
                  </>
                )}
              />
              <AdminPagination page={pendingResult.page} pageSize={ADMIN_ACTION_PAGE_SIZE} totalItems={pending.length} itemName="待审 Skill" onPageChange={setPendingPage} />
            </>
          )}
        </AdminTableSection>
      ) : (
        <AdminTableSection title={`最近处理（${decided.length}）`}>
          {reviews.isPending ? <AdminTableLoading label="正在加载 Skill 处理记录…" /> : decided.length === 0 ? <AdminEmptyState title="还没有处理记录" /> : (
            <>
              <SkillReviewTable
                records={decidedResult.items}
                action={item => (
                  <div className="admin-table-actions">
                    {item.status === 'approved' && <Button variant="secondary" size="sm" onClick={() => setDetail(item)}>查看</Button>}
                    {canOperate && item.status === 'approved' && (
                      <Button
                        variant={item.catalog_enabled ? 'secondary' : 'primary'}
                        size="sm"
                        className={item.catalog_enabled ? 'admin-danger-action' : ''}
                        onClick={() => setListingTarget({ item, enable: !item.catalog_enabled })}
                      >
                        {item.catalog_enabled ? '下架' : '恢复上架'}
                      </Button>
                    )}
                    {item.reason && <span className="admin-danger-text">拒绝理由：{item.reason}</span>}
                  </div>
                )}
              />
              <AdminPagination page={decidedResult.page} pageSize={ADMIN_DETAIL_PAGE_SIZE} totalItems={decided.length} itemName="处理记录" onPageChange={setDecidedPage} />
            </>
          )}
        </AdminTableSection>
      )}
      <SkillReviewDetailDialog item={detail} onClose={() => setDetail(null)} />
      <AdminListingDialog
        open={listingTarget !== null}
        resourceName={listingTarget?.item.skill_name ?? '该 Skill'}
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

function SkillReviewTable({ records, action, stickyActions = false }: { records: ReviewItem[]; action: (item: ReviewItem) => React.ReactNode; stickyActions?: boolean }) {
  return (
    <div className="admin-table-scroll">
      <table className={`admin-table admin-table-review${stickyActions ? ' admin-table--actions' : ''}`}>
        <thead><tr>{['名称', '提交方', '分类', '版本内容', '状态', '操作'].map(label => <th key={label}>{label}</th>)}</tr></thead>
        <tbody>
        {records.map(item => (
          <tr key={item.id} data-testid="review-row">
            <td className="admin-table-name">
              <div>{item.skill_name ?? '未命名 Skill'} <span className="admin-inline-version">v{item.version}</span></div>
              <div className="admin-table-subtitle">{item.description}</div>
            </td>
            <td>{item.owner_name}</td>
            <td><span className="admin-tag">{item.subject || '未分类'}</span></td>
            <td className="admin-table-mono">{item.file_count ?? 0} 个文件 · {formatBytes(item.total_bytes ?? 0)}</td>
            <td>{reviewStatusLabel(item)}{!item.responsibility_confirmed && <div className="admin-review-warning">未勾责任确认</div>}</td>
            <td>{action(item)}</td>
          </tr>
        ))}
        </tbody>
      </table>
    </div>
  )
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
  const [view, setView] = useState<'pending' | 'live' | 'closed'>('pending')
  const [pendingPage, setPendingPage] = useState(1)
  const [livePage, setLivePage] = useState(1)
  const [closedPage, setClosedPage] = useState(1)
  const [reasons, setReasons] = useState<Record<string, string>>({})
  const [failed, setFailed] = useState<Record<string, string>>({})
  const [probes, setProbes] = useState<Record<string, McpProbe>>({})
  const [detail, setDetail] = useState<AdminMcpServer | null>(null)
  const [listingTarget, setListingTarget] = useState<{ item: AdminMcpServer; enable: boolean } | null>(null)

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: mcpKeys.all })
  }
  const remember = (id: string, error: unknown) => {
    setFailed(current => ({ ...current, [id]: errorMessage(error) }))
  }

  const decide = useMutation({
    mutationFn: ({ id, approved, reason }: { id: string; approved: boolean; reason?: string }) =>
      decideApplication(id, approved, reason),
    async onSuccess() {
      setPendingPage(1)
      await refresh()
    },
    onError: (error, variables) => remember(variables.id, error),
  })
  const toggle = useMutation({
    mutationFn: ({ id, enabled, reason }: { id: string; enabled: boolean; reason?: string }) =>
      setEnabled(id, enabled, reason),
    async onSuccess() {
      setListingTarget(null)
      await refresh()
    },
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
  const pendingResult = paginateAdminItems(pending, pendingPage, ADMIN_ACTION_PAGE_SIZE)
  const liveResult = paginateAdminItems(live, livePage, ADMIN_DETAIL_PAGE_SIZE)
  const closedResult = paginateAdminItems(closed, closedPage, ADMIN_DETAIL_PAGE_SIZE)

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
    <div className="admin-page">
      <AdminPageHeader eyebrow="REVIEW · MCP" title="MCP 管理" description="审查外部能力的数据声明与工具清单；管理员还可在放行后测试连通性和启停服务。" pendingCount={pending.length} />
      {servers.isError && <div role="alert" className="admin-alert">{errorMessage(servers.error)}</div>}

      <AdminViewTabs
        label="切换 MCP 状态"
        value={view}
        options={[
          { value: 'pending', label: '待审核', count: pending.length },
          { value: 'live', label: '已放行', count: live.length },
          { value: 'closed', label: '已拒绝', count: closed.length },
        ]}
        onChange={setView}
      />

      {view === 'pending' && (
        <AdminTableSection title={`待审核 MCP Servers（${pending.length}）`}>
          {servers.isPending ? <AdminTableLoading label="正在加载 MCP 目录…" /> : pending.length === 0 ? <AdminEmptyState title="待审队列已清空" /> : (
            <>
              <McpTable
                records={pendingResult.items}
                probes={probes}
                failed={failed}
                action={item => (
                  <div className="admin-review-table-actions admin-review-table-actions--with-detail">
                    <input
                      value={reasons[item.id] ?? ''}
                      onChange={event => setReasons(current => ({ ...current, [item.id]: event.target.value }))}
                      placeholder="拒绝理由（拒绝时必填）"
                      aria-label={`${item.name} 的拒绝理由`}
                      className="admin-reason-input"
                    />
                    <Button variant="secondary" size="sm" onClick={() => setDetail(item)}>查看</Button>
                    <Button variant="secondary" size="sm" className="admin-danger-action" onClick={() => reject(item)} disabled={decide.isPending}>拒绝</Button>
                    <Button variant="primary" size="sm" onClick={() => decide.mutate({ id: item.id, approved: true })} disabled={decide.isPending}>通过</Button>
                  </div>
                )}
              />
              <AdminPagination page={pendingResult.page} pageSize={ADMIN_ACTION_PAGE_SIZE} totalItems={pending.length} itemName="待审 MCP" onPageChange={setPendingPage} />
            </>
          )}
        </AdminTableSection>
      )}

      {view === 'live' && (
        <AdminTableSection title={`已放行 MCP Servers（${live.length}）`}>
          {servers.isPending ? <AdminTableLoading label="正在加载 MCP 目录…" /> : live.length === 0 ? <AdminEmptyState title="还没有放行任何 MCP" /> : (
            <>
              <McpTable
                records={liveResult.items}
                probes={probes}
                failed={failed}
                action={item => (
                  <div className="admin-table-actions">
                    <Button variant="secondary" size="sm" onClick={() => setDetail(item)}>查看</Button>
                    {canOperate && <Button variant="secondary" size="sm" onClick={() => test.mutate(item.id)} disabled={test.isPending}>测试连接</Button>}
                    {canOperate && (item.status === 'enabled'
                      ? <Button variant="secondary" size="sm" className="admin-danger-action" onClick={() => setListingTarget({ item, enable: false })}>下架</Button>
                      : <Button variant="primary" size="sm" onClick={() => setListingTarget({ item, enable: true })}>恢复上架</Button>)}
                  </div>
                )}
              />
              <AdminPagination page={liveResult.page} pageSize={ADMIN_DETAIL_PAGE_SIZE} totalItems={live.length} itemName="已放行 MCP" onPageChange={setLivePage} />
            </>
          )}
        </AdminTableSection>
      )}

      {view === 'closed' && (
        <AdminTableSection title={`已拒绝（${closed.length}）`}>
          {servers.isPending ? <AdminTableLoading label="正在加载 MCP 目录…" /> : closed.length === 0 ? <AdminEmptyState title="还没有拒绝记录" /> : (
            <>
              <McpTable records={closedResult.items} probes={probes} failed={failed} action={() => null} />
              <AdminPagination page={closedResult.page} pageSize={ADMIN_DETAIL_PAGE_SIZE} totalItems={closed.length} itemName="已拒绝 MCP" onPageChange={setClosedPage} />
            </>
          )}
        </AdminTableSection>
      )}
      <McpDetailDialog item={detail} onClose={() => setDetail(null)} />
      <AdminListingDialog
        open={listingTarget !== null}
        resourceName={listingTarget?.item.name ?? '该 MCP'}
        enable={listingTarget?.enable ?? false}
        pending={toggle.isPending}
        error={toggle.isError ? errorMessage(toggle.error) : undefined}
        disableDescription="下架后会立即从 MCP 目录移除，新的运行无法再选择它；历史运行记录仍保留。"
        enableDescription="恢复后会重新进入 MCP 目录，并清空连续失败计数。"
        onConfirm={reason => {
          if (listingTarget) toggle.mutate({ id: listingTarget.item.id, enabled: listingTarget.enable, reason })
        }}
        onClose={() => setListingTarget(null)}
      />
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
    <div className="admin-table-scroll">
      <table className="admin-table admin-table-mcp admin-table--actions">
        <thead><tr>{headers.map(label => <th key={label}>{label}</th>)}</tr></thead>
        <tbody>
        {records.map(record => {
          const result = probes[record.id]
          return (
            <tr key={record.id} data-testid="mcp-row">
              <td className="admin-table-name">
                <div>{record.name}</div>
                <div className="admin-table-subtitle">{record.description}</div>
              </td>
              <td>{record.submitter_name}</td>
              <td className="admin-table-mono"><span className="admin-url" title={record.url}>{record.url}</span></td>
              <td>
                <div className="admin-table-subtitle">{record.tool_names.length} 个工具 · {record.latency_note || '未声明耗时'}</div>
                <div className="admin-tag-list">
                  {record.stores_user_data && <span className="admin-tag">存储用户数据</span>}
                  {record.sends_data_out && <span className="admin-tag">转发数据</span>}
                  {record.has_write_operation && <span className="admin-tag danger">有写操作 · 不可批</span>}
                </div>
              </td>
              <td>
                <div>{statusLabel(record)}</div>
                {record.disabled_reason && <div className="admin-warn-text">{record.disabled_reason}</div>}
                {record.failure_count > 0 && <div className="admin-warn-text">连续失败 {record.failure_count} 次</div>}
                {result && <div className={result.reachable ? 'admin-success-text' : 'admin-danger-text'}>
                  {result.reachable ? `连通，拿到 ${result.tool_names.length} 个工具` : '连不上'}
                  {result.undeclared.length > 0 && `；清单外多出：${result.undeclared.join('、')}`}
                  {result.declared_only.length > 0 && `；清单里有但实际没有：${result.declared_only.join('、')}`}
                </div>}
              </td>
              <td>
                {action(record)}
                {failed[record.id] && <div role="alert" className="admin-row-alert">{failed[record.id]}</div>}
              </td>
            </tr>
          )
        })}
        </tbody>
      </table>
    </div>
  )
}
