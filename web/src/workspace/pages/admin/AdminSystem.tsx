const SYSTEM_ITEMS = [
  { label: 'Worker', status: 'online' as const, detail: '2 个实例运行中' },
  { label: 'Postgres', status: 'online' as const, detail: '主库在线，备份正常' },
  { label: 'Redis', status: 'online' as const, detail: '内存使用 23%' },
  { label: 'MinIO', status: 'online' as const, detail: '对象存储在线' },
]

export function AdminSystem() {
  const sandboxUsed = 6, sandboxTotal = 20
  const sandboxPct = Math.round(sandboxUsed / sandboxTotal * 100)
  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '28px 32px', background: 'var(--bg)' }}>
      <div style={{ marginBottom: 24 }}>
        <div style={{ fontSize: 10, fontFamily: "'JetBrains Mono', monospace", textTransform: 'uppercase' as const, letterSpacing: '0.3em', color: 'var(--text-muted)', marginBottom: 4 }}>// SYSTEM STATUS</div>
        <h1 style={{ fontSize: 22, fontWeight: 700, color: 'var(--text-primary)' }}>系统状态</h1>
      </div>
      <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, padding: 24, marginBottom: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
          <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>沙箱池</div>
          <span style={{ fontSize: 13, fontFamily: "'JetBrains Mono', monospace", color: 'var(--text-secondary)' }}>{sandboxUsed} / {sandboxTotal} 占用</span>
        </div>
        <div style={{ height: 10, background: 'var(--border-light)', borderRadius: 5, overflow: 'hidden', marginBottom: 8 }}>
          <div style={{ height: '100%', width: `${sandboxPct}%`, background: sandboxPct > 80 ? 'var(--status-warn)' : 'var(--action)', borderRadius: 5 }} />
        </div>
        <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>剩余 {sandboxTotal - sandboxUsed} 个沙箱可用 · 单沙箱内存上限 2GB · gVisor 隔离</div>
      </div>
      <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, overflow: 'hidden' }}>
        <div style={{ padding: '14px 20px', borderBottom: '1px solid var(--border)', fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>服务状态</div>
        {SYSTEM_ITEMS.map((item, i) => (
          <div key={item.label} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '14px 20px', borderBottom: i < SYSTEM_ITEMS.length - 1 ? '1px solid var(--border-light)' : 'none' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <span style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--status-done)', display: 'inline-block', boxShadow: '0 0 0 2px rgba(16,185,129,0.2)' }} />
              <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>{item.label}</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
              <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{item.detail}</span>
              <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--status-done)' }}>◉ 在线</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
