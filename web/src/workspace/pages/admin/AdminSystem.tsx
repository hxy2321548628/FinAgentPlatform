import { AdminPageHeader, AdminTableSection } from './AdminUi'
import { pageStyle } from './AdminStyles'

const SYSTEM_ITEMS = [
  { label: 'Worker', detail: '2 个实例运行中' },
  { label: 'Postgres', detail: '主库在线，备份正常' },
  { label: 'Redis', detail: '内存使用 23%' },
  { label: 'MinIO', detail: '对象存储在线' },
]

export function AdminSystem() {
  const sandboxUsed = 6
  const sandboxTotal = 20
  const sandboxPct = Math.round(sandboxUsed / sandboxTotal * 100)

  return (
    <div style={pageStyle}>
      <AdminPageHeader eyebrow="// SYSTEM STATUS" title="系统状态" />

      <AdminTableSection title="沙箱池">
        <div style={{ padding: '20px 18px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
            <span style={{ color: 'var(--text-secondary)', fontSize: 13 }}>当前资源占用</span>
            <span style={{ color: 'var(--text-secondary)', fontFamily: "'JetBrains Mono', monospace", fontSize: 13 }}>{sandboxUsed} / {sandboxTotal}</span>
          </div>
          <div style={{ height: 10, marginBottom: 8, overflow: 'hidden', borderRadius: 5, background: 'var(--border-light)' }}>
            <div style={{ width: `${sandboxPct}%`, height: '100%', borderRadius: 5, background: sandboxPct > 80 ? 'var(--status-warn)' : 'var(--action)' }} />
          </div>
          <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>剩余 {sandboxTotal - sandboxUsed} 个沙箱可用 · 单沙箱内存上限 2GB · gVisor 隔离</div>
        </div>
      </AdminTableSection>

      <AdminTableSection title="服务状态">
        {SYSTEM_ITEMS.map((item, index) => (
          <div key={item.label} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '14px 18px', borderBottom: index < SYSTEM_ITEMS.length - 1 ? '1px solid var(--border-light)' : 'none' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: 'var(--status-done)', boxShadow: '0 0 0 2px rgba(16,185,129,0.2)' }} />
              <span style={{ color: 'var(--text-primary)', fontSize: 14, fontWeight: 600 }}>{item.label}</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
              <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>{item.detail}</span>
              <span style={{ color: 'var(--status-done)', fontSize: 12, fontWeight: 600 }}>● 在线</span>
            </div>
          </div>
        ))}
      </AdminTableSection>
    </div>
  )
}
