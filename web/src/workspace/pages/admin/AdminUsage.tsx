import { AdminPageHeader, AdminTableSection } from './AdminUi'
import { cellStyle, monoCellStyle, nameCellStyle, pageStyle, tableStyle, thStyle } from './AdminStyles'

const MOCK_STATS = { totalRuns: 312, totalTokens: 4280000, totalCost: 42.8, activeUsers: 18 }
const MOCK_USER_USAGE = [
  { name: '张老师', tokens: 45230, runs: 12, cost: 3.2 },
  { name: '李教授', tokens: 38910, runs: 9, cost: 2.8 },
  { name: '赵同学', tokens: 21430, runs: 7, cost: 1.5 },
  { name: '陈研究生', tokens: 18760, runs: 5, cost: 1.3 },
  { name: '孙老师', tokens: 15200, runs: 4, cost: 1.1 },
]

export function AdminUsage() {
  return (
    <div style={pageStyle}>
      <AdminPageHeader eyebrow="// USAGE DASHBOARD" title="用量看板" badgeText="2026-08-01 ~ 2026-08-09" />

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 14, marginBottom: 24 }}>
        {[
          { label: 'TOTAL RUNS', value: MOCK_STATS.totalRuns.toLocaleString(), unit: '次分析' },
          { label: 'TOKENS USED', value: `${(MOCK_STATS.totalTokens / 1000000).toFixed(1)}M`, unit: 'tokens 消耗' },
          { label: 'EST. COST', value: `¥${MOCK_STATS.totalCost.toFixed(1)}`, unit: '估算费用', accent: true },
          { label: 'ACTIVE USERS', value: MOCK_STATS.activeUsers.toString(), unit: '活跃用户' },
        ].map(stat => (
          <div key={stat.label} style={{ minWidth: 0, padding: '18px 20px', border: '1px solid var(--border)', borderRadius: 10, background: 'var(--surface)' }}>
            <div style={{ marginBottom: 8, color: 'var(--text-muted)', fontFamily: "'JetBrains Mono', monospace", fontSize: 10, letterSpacing: '0.12em' }}>{stat.label}</div>
            <div style={{ marginBottom: 4, color: stat.accent ? 'var(--action)' : 'var(--text-primary)', fontFamily: "'JetBrains Mono', monospace", fontSize: 26, fontWeight: 800, lineHeight: 1 }}>{stat.value}</div>
            <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>{stat.unit}</div>
          </div>
        ))}
      </div>

      <AdminTableSection title="用量排行（本月）">
        <table style={tableStyle}>
          <thead><tr>{['排名', '用户', '本月 Tokens', '本月 Run 数', '估算费用'].map(label => <th key={label} style={thStyle}>{label}</th>)}</tr></thead>
          <tbody>
            {MOCK_USER_USAGE.map((usage, index) => (
              <tr key={usage.name} style={{ borderBottom: index < MOCK_USER_USAGE.length - 1 ? '1px solid var(--border-light)' : 'none' }}>
                <td style={{ ...monoCellStyle, color: index < 3 ? 'var(--action)' : 'var(--text-muted)', fontWeight: index < 3 ? 700 : 400 }}>#{index + 1}</td>
                <td style={nameCellStyle}>{usage.name}</td>
                <td style={monoCellStyle}>{usage.tokens.toLocaleString()}</td>
                <td style={cellStyle}>{usage.runs}</td>
                <td style={{ ...monoCellStyle, color: 'var(--action)', fontWeight: 500 }}>¥{usage.cost}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </AdminTableSection>
    </div>
  )
}
