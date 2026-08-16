import { NavLink, useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { Logo } from './Logo'
import { AUTH_QUERY_KEY, me } from '../api/auth'

const NAV_LINKS = [
  { to: '/',             label: '首页',     end: true },
  { to: '/scenarios',   label: '研究范式' },
  { to: '/capabilities',label: '技术底座' },
  { to: '/data',        label: '数据要素' },
  { to: '/marketplace', label: '智能体市场' },
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
        <Logo height={24} />
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
