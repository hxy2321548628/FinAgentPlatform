import { NavLink, useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { AUTH_QUERY_KEY, me } from '../api/auth'

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
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const handleWorkspaceEntry = async () => {
    try {
      await queryClient.fetchQuery({ queryKey: AUTH_QUERY_KEY, queryFn: () => me({ redirectOn401: false }) })
      navigate('/workspace')
    } catch {
      navigate('/login')
    }
  }

  return (
    <nav className="navbar">
      <NavLink
        to="/"
        style={{ display: 'flex', alignItems: 'center', gap: 10, textDecoration: 'none', marginRight: 20, flexShrink: 0 }}
      >
        <svg viewBox="12 3 24 34" fill="currentColor" style={{ height: 24, width: 'auto', color: 'var(--logo-green)', flexShrink: 0 }} aria-hidden="true">
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
              transition: 'background 0.2s, color 0.2s',
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

      <button
        type="button"
        onClick={handleWorkspaceEntry}
        style={{
          marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', height: 34,
          padding: '0 16px', borderRadius: 7, background: 'var(--action)', color: '#fff',
          border: 'none', cursor: 'pointer', fontFamily: 'inherit', fontSize: 13,
          fontWeight: 600, whiteSpace: 'nowrap',
        }}
      >
        进入工作台 →
      </button>
    </nav>
  )
}
