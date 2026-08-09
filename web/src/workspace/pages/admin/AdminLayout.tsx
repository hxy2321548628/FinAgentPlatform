import { NavLink, Outlet, useNavigate } from 'react-router-dom'

const ADMIN_NAV = [
  { to: '/workspace/admin/users', label: '用户管理', icon: '👥' },
  { to: '/workspace/admin/agents', label: '智能体审核', icon: '🔍' },
  { to: '/workspace/admin/usage', label: '用量看板', icon: '📊' },
  { to: '/workspace/admin/system', label: '系统状态', icon: '🖥' },
]

export function AdminLayout() {
  const navigate = useNavigate()
  return (
    <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
      <div style={{ width: 180, flexShrink: 0, background: 'var(--surface)', borderRight: '1px solid var(--border)', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <div style={{ padding: '16px 16px 10px' }}>
          <div style={{ fontSize: 10, fontFamily: "'JetBrains Mono', monospace", textTransform: 'uppercase' as const, letterSpacing: '0.2em', color: 'var(--text-muted)', marginBottom: 4 }}>// ADMIN</div>
          <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)' }}>管理后台</div>
        </div>
        <div style={{ height: 1, background: 'var(--border-light)' }} />
        <nav style={{ flex: 1, padding: '6px 8px' }}>
          {ADMIN_NAV.map(item => (
            <NavLink key={item.to} to={item.to} style={({ isActive }) => ({ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 10px', borderRadius: 6, marginBottom: 2, fontSize: 13, textDecoration: 'none', background: isActive ? 'var(--action-light)' : 'transparent', color: isActive ? 'var(--action)' : 'var(--text-secondary)', fontWeight: isActive ? 600 : 400, transition: 'background 0.15s, color 0.15s' })}>
              <span style={{ fontSize: 14 }}>{item.icon}</span>
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div style={{ padding: '10px 8px', borderTop: '1px solid var(--border-light)' }}>
          <button onClick={() => navigate('/workspace')} style={{ width: '100%', padding: '7px 10px', display: 'flex', alignItems: 'center', gap: 8, background: 'none', border: 'none', cursor: 'pointer', fontSize: 12, color: 'var(--text-muted)', fontFamily: 'inherit', borderRadius: 6 }}>← 返回工作台</button>
        </div>
      </div>
      <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
        <Outlet />
      </div>
    </div>
  )
}
