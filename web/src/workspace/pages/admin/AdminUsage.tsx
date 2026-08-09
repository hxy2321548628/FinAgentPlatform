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
    <div style={{ flex: 1, overflowY: 'auto', padding: '28px 32px', background: 'var(--bg)' }}>
      <div style={{ marginBottom: 24 }}>
        <div style={{ fontSize: 10, fontFamily: "'JetBrains Mono', monospace", textTransform: 'uppercase' as const, letterSpacing: '0.3em', color: 'var(--text-muted)', marginBottom: 4 }}>// USAGE DASHBOARD</div>
        <h1 style={{ fontSize: 22, fontWeight: 700, color: 'var(--text-primary)' }}>用量看板</h1>
        <p style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 4 }}>统计周期：2026-08-01 ~ 2026-08-09</p>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14, marginBottom: 28 }}>
        {[
          { label: 'TOTAL RUNS', value: MOCK_STATS.totalRuns.toLocaleString(), unit: '次分析' },
          { label: 'TOKENS USED', value: (MOCK_STATS.totalTokens / 1000000).toFixed(1) + 'M', unit: 'tokens 消耗' },
          { label: 'EST. COST', value: '¥' + MOCK_STATS.totalCost.toFixed(1), unit: '估算费用', accent: true },
          { label: 'ACTIVE USERS', value: MOCK_STATS.activeUsers.toString(), unit: '活跃用户' },
        ].map(s => (
          <div key={s.label} style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, padding: '18px 20px' }}>
            <div style={{ fontSize: 10, fontFamily: "'JetBrains Mono', monospace", textTransform: 'uppercase' as const, letterSpacing: '0.12em', color: 'var(--text-muted)', marginBottom: 8 }}>{s.label}</div>
            <div style={{ fontSize: 26, fontWeight: 800, color: s.accent ? 'var(--action)' : 'var(--text-primary)', fontFamily: "'JetBrains Mono', monospace", lineHeight: 1, marginBottom: 4 }}>{s.value}</div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{s.unit}</div>
          </div>
        ))}
      </div>
      <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, overflow: 'hidden' }}>
        <div style={{ padding: '14px 20px', borderBottom: '1px solid var(--border)', fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>用量排行（本月）</div>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr>{['排名','用户','本月 Tokens','本月 Run 数','估算费用'].map(h => <th key={h} style={{ padding: '10px 20px', textAlign: 'left' as const, fontSize: 11, color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase' as const, letterSpacing: '0.08em', borderBottom: '1px solid var(--border-light)', background: 'var(--bg)' }}>{h}</th>)}</tr>
          </thead>
          <tbody>
            {MOCK_USER_USAGE.map((u, i) => (
              <tr key={u.name} style={{ borderBottom: i < MOCK_USER_USAGE.length - 1 ? '1px solid var(--border-light)' : 'none' }}>
                <td style={{ padding: '12px 20px', fontSize: 12, fontFamily: "'JetBrains Mono', monospace", color: i < 3 ? 'var(--action)' : 'var(--text-muted)', fontWeight: i < 3 ? 700 : 400 }}>#{i + 1}</td>
                <td style={{ padding: '12px 20px', fontWeight: 500, color: 'var(--text-primary)' }}>{u.name}</td>
                <td style={{ padding: '12px 20px', fontFamily: "'JetBrains Mono', monospace", fontSize: 12, color: 'var(--text-secondary)' }}>{u.tokens.toLocaleString()}</td>
                <td style={{ padding: '12px 20px', color: 'var(--text-secondary)' }}>{u.runs}</td>
                <td style={{ padding: '12px 20px', fontFamily: "'JetBrains Mono', monospace", fontSize: 12, color: 'var(--action)', fontWeight: 500 }}>¥{u.cost}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
