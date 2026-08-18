import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { errorMessage } from '../../../api/request'
import { usageKeys, usageRanking } from '../../../api/usage'
import { ADMIN_LIST_PAGE_SIZE, paginateAdminItems } from './AdminPaging'
import { AdminEmptyState, AdminPageHeader, AdminPagination, AdminTableLoading, AdminTableSection } from './AdminUi'

function monthLabel(): string {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
}

export function AdminUsage() {
  const [page, setPage] = useState(1)
  const ranking = useQuery({ queryKey: usageKeys.ranking(), queryFn: usageRanking })
  const data = ranking.data
  const items = data?.items ?? []
  const result = paginateAdminItems(items, page, ADMIN_LIST_PAGE_SIZE)

  return (
    <div className="admin-page">
      <AdminPageHeader eyebrow="OPERATIONS · USAGE" title="用量看板" description="查看本月模型调用、Token 消耗、费用估算与账号用量前 20 名。" badgeText={`${monthLabel()} 本月累计`} />

      {ranking.isError && <div role="alert" className="admin-alert">{errorMessage(ranking.error)}</div>}

      {/* **「没接账本」要说出来，不能显示成一排 0。** 那样看板会像在说
          「这个月全院一次都没用过」，而真相是它根本没在记 */}
      {data && !data.available && (
        <div role="status" className="admin-notice warning">
          用量账本（Langfuse）未接入或暂时不可达，因此这一页没有数据。
          配置 <code>LANGFUSE_BASE_URL</code> 等三项后重启 api 即可。
        </div>
      )}

      <div className="admin-stat-grid">
        {[
          { label: 'TOKENS USED', value: data?.available ? formatTokens(data.total.tokens) : '—', unit: 'tokens 消耗' },
          { label: 'MODEL CALLS', value: data?.available ? data.total.observations.toLocaleString() : '—', unit: '次模型调用' },
          // **单价没注册时费用恒为 0**，这时显示「未计价」比显示 $0.00 诚实
          {
            label: 'EST. COST',
            value: data?.available ? (data.total.cost > 0 ? `$${data.total.cost.toFixed(2)}` : '未计价') : '—',
            unit: '估算费用',
            accent: true,
          },
        ].map(stat => (
          <div key={stat.label} className="admin-stat-card">
            <div className="admin-stat-label">{stat.label}</div>
            <div className={`admin-stat-value${stat.accent ? ' accent' : ''}`}>{stat.value}</div>
            <div className="admin-stat-unit">{stat.unit}</div>
          </div>
        ))}
      </div>

      <AdminTableSection title="用量 Top 20（本月）">
        {ranking.isPending ? (
          <AdminTableLoading label="正在加载用量排行…" />
        ) : items.length === 0 ? (
          <AdminEmptyState title={data?.available ? '本月还没有人使用' : '暂无数据'} />
        ) : (
          <>
            <div className="admin-table-scroll">
              <table className="admin-table admin-table-usage">
                <thead><tr>{['排名', '用户', '本月 Tokens', '模型调用', '估算费用'].map(label => <th key={label}>{label}</th>)}</tr></thead>
                <tbody>
                  {result.items.map((one, index) => {
                    const rank = (result.page - 1) * ADMIN_LIST_PAGE_SIZE + index + 1
                    return (
                      <tr key={one.user_id}>
                        <td className={`admin-table-mono admin-rank${rank <= 3 ? ' top' : ''}`}>#{rank}</td>
                        <td className="admin-table-name">{one.name}</td>
                        <td className="admin-table-mono">{one.tokens.toLocaleString()}</td>
                        <td>{one.observations}</td>
                        <td className="admin-table-mono admin-cost">{one.cost > 0 ? `$${one.cost.toFixed(2)}` : '—'}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            <AdminPagination page={result.page} pageSize={ADMIN_LIST_PAGE_SIZE} totalItems={items.length} itemName="账号" onPageChange={setPage} />
          </>
        )}
      </AdminTableSection>
    </div>
  )
}

function formatTokens(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`
  return String(value)
}
