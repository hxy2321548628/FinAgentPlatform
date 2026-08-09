import { useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'

const LOGO_PATH_1 = 'M24.22,27.73l1.05-2c.36-.69.73-1.38,1.08-2.07a.26.26,0,0,1,.27-.17h3.83a.26.26,0,0,1,.27.18c1.44,3.06,3,6.08,4.65,9a.23.23,0,0,0,.08.16H27.09a.3.3,0,0,1-.32-.19q-1.2-2.34-2.42-4.66l-.14-.25c-.05.09-.1.16-.13.23l-2.44,4.7a.25.25,0,0,1-.26.17H13l.4-.83c1.53-2.72,2.94-5.5,4.27-8.33a.35.35,0,0,1,.38-.24h3.74a.27.27,0,0,1,.28.18l2,3.84Z'
const LOGO_PATH_2 = 'M24.21,4.19a82.908,82.908,0,0,0,2.43,9.16,85.1,85.1,0,0,0,3.43,8.85H18.33a79,79,0,0,0,3.47-8.86,84.311,84.311,0,0,0,2.41-9.15Zm0,16.18A1.3,1.3,0,1,0,23,19.07a1.26,1.26,0,0,0,1.23,1.3Z'

const NAV_LINKS = [
  { to: '/',             label: '首页',     end: true },
  { to: '/marketplace', label: '智能体市场' },
  { to: '/scenarios',   label: '研究范式' },
  { to: '/capabilities',label: '技术底座' },
  { to: '/data',        label: '数据要素' },
]

export function Navbar() {
  const [open, setOpen] = useState(false)
  const navigate = useNavigate()

  const handleLogout = () => {
    setOpen(false)
    navigate('/login')
  }

  return (
    <nav className="navbar">
      <NavLink
        to="/"
        style={{ display: 'flex', alignItems: 'center', gap: 10, textDecoration: 'none', marginRight: 20, flexShrink: 0 }}
      >
        <svg viewBox="12 3 24 34" fill="currentColor" style={{ height: 24, width: 'auto', color: 'var(--logo-red)', flexShrink: 0 }} aria-hidden="true">
          <path d={LOGO_PATH_1} /><path d={LOGO_PATH_2} />
        </svg>
        <span style={{ fontSize: 17, fontWeight: 700, color: 'var(--text-primary)', letterSpacing: '0.02em' }}>
          FinAgentPlatform
        </span>
      </NavLink>

      <div style={{ display: 'flex', gap: 4, flex: 1 }}>
        {NAV_LINKS.map(({ to, label, end }) => (
          <NavLink
            key={to} to={to} end={end}
            style={({ isActive }) => ({
              fontSize: 13, textDecoration: 'none', padding: '5px 12px', borderRadius: 6,
              transition: 'all 0.2s',
              background: isActive ? 'var(--brand)' : 'transparent',
              color: isActive ? '#fff' : 'var(--text-secondary)',
              fontWeight: isActive ? 500 : 400,
              whiteSpace: 'nowrap',
            })}
          >
            {label}
          </NavLink>
        ))}
      </div>

      <div style={{ marginLeft: 'auto', position: 'relative' }}>
        <div
          onClick={(e) => { e.stopPropagation(); setOpen(o => !o) }}
          style={{
            width: 32, height: 32, borderRadius: '50%',
            background: 'var(--action-light)', border: '1px solid var(--action-border)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: 'var(--action)', fontSize: 13, fontWeight: 600, cursor: 'pointer', userSelect: 'none',
          }}
        >张</div>

        {open && (
          <>
            <div onClick={() => setOpen(false)} style={{ position: 'fixed', inset: 0, zIndex: 199 }} />
            <div className="avatar-dropdown">
              <div style={{ padding: '8px 12px 10px' }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>张老师</div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 1 }}>zhang@fin.edu.cn</div>
              </div>
              <div style={{ height: 1, background: 'var(--border-light)', margin: '4px 0' }} />
              <NavLink to="/workspace" onClick={() => setOpen(false)} style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '8px 12px', borderRadius: 7, fontSize: 13, color: 'var(--text-primary)', textDecoration: 'none', fontWeight: 600 }}>
                进入工作台 →
              </NavLink>
              <div style={{ height: 1, background: 'var(--border-light)', margin: '4px 0' }} />
              <NavLink to="/settings" onClick={() => setOpen(false)} style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '8px 12px', borderRadius: 7, fontSize: 13, color: 'var(--text-secondary)', textDecoration: 'none' }}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
                设置
              </NavLink>
              <div style={{ height: 1, background: 'var(--border-light)', margin: '4px 0' }} />
              <button onClick={handleLogout} style={{ display: 'flex', width: '100%', alignItems: 'center', gap: 9, padding: '8px 12px', borderRadius: 7, fontSize: 13, color: '#DC2626', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit', textAlign: 'left' }}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
                退出登录
              </button>
            </div>
          </>
        )}
      </div>
    </nav>
  )
}
