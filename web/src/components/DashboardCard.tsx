export function DashboardCard() {
  const logs = [
    { icon: '✓', cls: '#10B981', name: 'read_file',  arg: 'portfolio.csv',           time: '0.1s' },
    { icon: '✓', cls: '#10B981', name: 'write_file', arg: 'volatility_analysis.py',  time: '0.1s' },
    { icon: '◉', cls: '#1749C4', name: 'execute',    arg: 'python volatility_analysis.py', time: '' },
    { icon: '○', cls: '#8E9BB0', name: 'write_file', arg: 'outputs/vol_chart.png',   time: '' },
  ]

  return (
    <div style={{
      background: 'var(--surface)', borderRadius: 10,
      border: '1px solid var(--border)',
      boxShadow: '0 4px 8px rgba(11,46,92,0.06), 0 12px 40px rgba(11,46,92,0.10)',
      overflow: 'hidden', width: 460, flexShrink: 0,
    }}>
      {/* 标题栏 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '12px 16px', background: 'var(--input-bg)', borderBottom: '1px solid var(--border-light)' }}>
        {[0,1,2].map(i => <div key={i} style={{ width: 10, height: 10, borderRadius: '50%', background: 'var(--border)' }} />)}
        <span style={{ fontSize: 11, color: 'var(--text-muted)', marginLeft: 8, fontFamily: 'monospace', letterSpacing: '0.04em' }}>
          agent_executor · run_0x8B3F
        </span>
      </div>
      {/* 内容 */}
      <div style={{ padding: 18, fontFamily: "'JetBrains Mono', monospace", fontSize: 11.5, lineHeight: 1.9 }}>
        <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 8 }}>任务：持仓 CSV 年化波动率分析</div>
        <hr style={{ border: 'none', borderTop: '1px solid var(--border-light)', margin: '8px 0' }} />
        {logs.map((l, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
            <span style={{ color: l.cls, minWidth: 12 }}>{l.icon}</span>
            <span style={{ minWidth: 76, color: 'var(--text-secondary)' }}>{l.name}</span>
            <span style={{ color: 'var(--text-muted)', flex: 1, fontSize: 11 }}>{l.arg}</span>
            {l.time && <span style={{ color: 'var(--text-muted)', fontSize: 10 }}>{l.time}</span>}
          </div>
        ))}
        <span style={{ paddingLeft: 20, color: 'var(--text-muted)', fontSize: 11, display: 'block', lineHeight: 1.7 }}>└─ Computing sector volatility...</span>
        <span style={{ paddingLeft: 20, color: 'var(--text-muted)', fontSize: 11, display: 'block', lineHeight: 1.7 }}>└─ Annualizing: 252 trading days</span>
        <hr style={{ border: 'none', borderTop: '1px solid var(--border-light)', margin: '8px 0' }} />
        <div style={{ color: 'var(--status-active)', fontWeight: 500 }}>◉ 执行中 · 已用时 3.2s</div>
      </div>
    </div>
  )
}
