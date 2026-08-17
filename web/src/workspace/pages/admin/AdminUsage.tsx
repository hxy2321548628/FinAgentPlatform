import { useQuery } from '@tanstack/react-query'
import { errorMessage } from '../../../api/request'
import { usageKeys, usageRanking } from '../../../api/usage'
import { AdminPageHeader, AdminTableSection } from './AdminUi'
import { cellStyle, monoCellStyle, nameCellStyle, pageStyle, tableStyle, thStyle } from './AdminStyles'

function monthLabel(): string {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
}

export function AdminUsage() {
  const ranking = useQuery({ queryKey: usageKeys.ranking(), queryFn: usageRanking })
  const data = ranking.data
  const items = data?.items ?? []

  return (
    <div style={pageStyle}>
      <AdminPageHeader eyebrow="// USAGE DASHBOARD" title="用量看板" badgeText={`${monthLabel()} 本月累计`} />

      {ranking.isError && <div role="alert" style={alertStyle}>{errorMessage(ranking.error)}</div>}

      {/* **「没接账本」要说出来，不能显示成一排 0。** 那样看板会像在说
          「这个月全院一次都没用过」，而真相是它根本没在记 */}
      {data && !data.available && (
        <div role="status" style={noticeStyle}>
          用量账本（Langfuse）未接入或暂时不可达，因此这一页没有数据。
          配置 <code>LANGFUSE_BASE_URL</code> 等三项后重启 api 即可。
        </div>
      )}

      <div className="admin-stat-grid" style={{ display: 'grid', gap: 14, marginBottom: 24 }}>
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
          <div key={stat.label} style={{ minWidth: 0, padding: '18px 20px', border: '1px solid var(--border)', borderRadius: 10, background: 'var(--surface)' }}>
            <div style={{ marginBottom: 8, color: 'var(--text-muted)', fontFamily: "'JetBrains Mono', monospace", fontSize: 10, letterSpacing: '0.12em' }}>{stat.label}</div>
            <div style={{ marginBottom: 4, color: stat.accent ? 'var(--action)' : 'var(--text-primary)', fontFamily: "'JetBrains Mono', monospace", fontSize: 26, fontWeight: 800, lineHeight: 1 }}>{stat.value}</div>
            <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>{stat.unit}</div>
          </div>
        ))}
      </div>

      <AdminTableSection title="用量排行（本月）">
        {ranking.isPending ? (
          <div style={emptyStyle}>正在加载…</div>
        ) : items.length === 0 ? (
          <div style={emptyStyle}>{data?.available ? '本月还没有人用过' : '暂无数据'}</div>
        ) : (
          <table style={tableStyle}>
            <thead><tr>{['排名', '用户', '本月 Tokens', '模型调用', '估算费用'].map(label => <th key={label} style={thStyle}>{label}</th>)}</tr></thead>
            <tbody>
              {items.map((one, index) => (
                <tr key={one.user_id} style={{ borderBottom: index < items.length - 1 ? '1px solid var(--border-light)' : 'none' }}>
                  <td style={{ ...monoCellStyle, color: index < 3 ? 'var(--action)' : 'var(--text-muted)', fontWeight: index < 3 ? 700 : 400 }}>#{index + 1}</td>
                  <td style={nameCellStyle}>{one.name}</td>
                  <td style={monoCellStyle}>{one.tokens.toLocaleString()}</td>
                  <td style={cellStyle}>{one.observations}</td>
                  <td style={{ ...monoCellStyle, color: 'var(--action)', fontWeight: 500 }}>{one.cost > 0 ? `$${one.cost.toFixed(2)}` : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
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

const alertStyle: React.CSSProperties = { marginBottom: 14, padding: '9px 12px', border: '1px solid #FECACA', borderRadius: 6, background: 'var(--danger-bg)', color: 'var(--danger)', fontSize: 13 }
const noticeStyle: React.CSSProperties = { marginBottom: 16, padding: '12px 14px', border: '1px solid #FDE68A', borderRadius: 8, background: 'var(--warn-bg)', color: 'var(--warn)', fontSize: 13, lineHeight: 1.7 }
const emptyStyle: React.CSSProperties = { padding: '48px 20px', textAlign: 'center', color: 'var(--text-muted)', fontSize: 13 }
