import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { AUTH_QUERY_KEY, me } from '../../../api/auth'

const LOGO_PATH_1 = 'M24.22,27.73l1.05-2c.36-.69.73-1.38,1.08-2.07a.26.26,0,0,1,.27-.17h3.83a.26.26,0,0,1,.27.18c1.44,3.06,3,6.08,4.65,9a.23.23,0,0,0,.08.16H27.09a.3.3,0,0,1-.32-.19q-1.2-2.34-2.42-4.66l-.14-.25c-.05.09-.1.16-.13.23l-2.44,4.7a.25.25,0,0,1-.26.17H13l.4-.83c1.53-2.72,2.94-5.5,4.27-8.33a.35.35,0,0,1,.38-.24h3.74a.27.27,0,0,1,.28.18l2,3.84Z'
const LOGO_PATH_2 = 'M24.21,4.19a82.908,82.908,0,0,0,2.43,9.16,85.1,85.1,0,0,0,3.43,8.85H18.33a79,79,0,0,0,3.47-8.86,84.311,84.311,0,0,0,2.41-9.15Zm0,16.18A1.3,1.3,0,1,0,23,19.07a1.26,1.26,0,0,0,1.23,1.3Z'

const ADMIN_GROUPS = [
  {
    label: '账号与权限',
    links: [
      { to: '/admin/users', label: '用户管理', icon: <><circle cx="9" cy="7" r="4"/><path d="M17 11a4 4 0 1 0 0-8M2 21a7 7 0 0 1 14 0M16 14a6 6 0 0 1 6 6"/></> },
    ],
  },
  {
    label: '内容与能力',
    links: [
      // **场景与智能体共用这一个审核入口**：它们在库里是同一张表，
      // 区别只是「挂没挂子智能体」（P6-decision G2）。原来那个「场景管理」页
      // 审的是同一个队列，两个入口只会让两边状态看起来不一致
      { to: '/admin/agents', label: '场景与智能体审核', icon: <><circle cx="12" cy="8" r="4"/><path d="M20 21a8 8 0 1 0-16 0"/><path d="m17 14 2 2 4-4"/></> },
      { to: '/admin/skills', label: 'Skill 管理', icon: <><path d="m12 2 2.4 4.86 5.6.81-4 3.9.94 5.51L12 14.5l-4.94 2.58L8 11.57l-4-3.9 5.6-.81L12 2z"/><path d="M5 21h14"/></> },
      { to: '/admin/mcp', label: 'MCP 管理', icon: <><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/><path d="M10 6.5h4a3.5 3.5 0 0 1 3.5 3.5v4M14 17.5h-4A3.5 3.5 0 0 1 6.5 14v-4"/></> },
    ],
  },
  {
    label: '运营与系统',
    links: [
      { to: '/admin/usage', label: '用量看板', icon: <><path d="M3 3v18h18"/><path d="m7 16 4-5 4 3 5-7"/></> },
      { to: '/admin/system', label: '系统状态', icon: <><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06M19.4 9a1.65 1.65 0 0 1 .33-1.82l.06-.06M15 4.6a1.65 1.65 0 0 0 1-1.51V3M9 4.6a1.65 1.65 0 0 1-1-1.51V3M4.6 9a1.65 1.65 0 0 0-1.51-1H3M4.6 15a1.65 1.65 0 0 1-1.51 1H3M9 19.4a1.65 1.65 0 0 0-1 1.51V21M15 19.4a1.65 1.65 0 0 1 1 1.51V21"/></> },
    ],
  },
]

export function AdminLayout() {
  const navigate = useNavigate()
  const current = useQuery({ queryKey: AUTH_QUERY_KEY, queryFn: () => me() })
  // reviewer 只看得到 Agent 与 Skill 两个审核入口；其余后台功能仍只属于 admin。
  const reviewerOnly = current.data?.role === 'reviewer'
  const visible = reviewerOnly
    ? ADMIN_GROUPS.map(group => ({ ...group, links: group.links.filter(link => ['/admin/agents', '/admin/skills'].includes(link.to)) })).filter(
        group => group.links.length > 0,
      )
    : ADMIN_GROUPS

  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden', background: 'var(--bg)' }}>
      <aside style={{ width: 220, flexShrink: 0, background: 'var(--ws-sidebar-bg)', color: '#fff', display: 'flex', flexDirection: 'column', height: '100vh', overflow: 'hidden' }}>
        <div style={{ height: 72, flexShrink: 0, padding: '0 16px', display: 'flex', alignItems: 'center', gap: 9, borderBottom: '1px solid var(--ws-sidebar-border)' }}>
          <svg viewBox="12 3 24 34" fill="currentColor" style={{ height: 22, width: 'auto', color: '#0E8A7B' }} aria-hidden="true"><path d={LOGO_PATH_1}/><path d={LOGO_PATH_2}/></svg>
          <div><div style={{ fontSize: 14, fontWeight: 700, lineHeight: 1.2 }}>FinAgentPlatform</div><div style={{ fontSize: 10, color: 'var(--ws-sidebar-text)', marginTop: 2 }}>管理后台</div></div>
        </div>

        <nav style={{ flex: 1, overflowY: 'auto', padding: '8px 0 10px' }}>
          {visible.map((group, index) => (
            <div key={group.label} style={{ paddingTop: index === 0 ? 0 : 6, borderTop: index === 0 ? 'none' : '1px solid var(--ws-sidebar-border)', marginTop: index === 0 ? 0 : 6 }}>
              <div style={{ padding: '7px 16px 5px', fontSize: 10, color: 'var(--ws-sidebar-text)', letterSpacing: '0.12em' }}>{group.label}</div>
              {group.links.map(link => (
                <NavLink key={link.to} to={link.to} style={({ isActive }) => ({
                  display: 'flex', alignItems: 'center', gap: 10, padding: '9px 16px',
                  borderLeft: isActive ? '3px solid var(--action)' : '3px solid transparent',
                  background: isActive ? 'var(--ws-sidebar-accent)' : 'transparent',
                  color: isActive ? 'var(--ws-sidebar-active)' : 'var(--ws-sidebar-text)',
                  textDecoration: 'none', fontSize: 13, fontWeight: isActive ? 600 : 400,
                  transition: 'background 0.15s, color 0.15s',
                })}>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">{link.icon}</svg>
                  {link.label}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>

        <div style={{ borderTop: '1px solid var(--ws-sidebar-border)' }}>
          <button type="button" onClick={() => navigate('/workspace')} style={{
            display: 'flex', alignItems: 'center', gap: 10, width: '100%', padding: '9px 16px',
            border: 'none', background: 'none', color: 'var(--ws-sidebar-text)', textAlign: 'left',
            cursor: 'pointer', fontFamily: 'inherit', fontSize: 13,
          }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
            返回工作台
          </button>
          <div style={{ padding: '12px 16px', borderTop: '1px solid var(--ws-sidebar-border)', display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{ width: 32, height: 32, borderRadius: '50%', background: 'var(--action)', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, fontWeight: 700, flexShrink: 0 }}>{current.data?.name.at(0) ?? '·'}</div>
            <div style={{ minWidth: 0 }}><div style={{ fontSize: 13, fontWeight: 600, color: '#fff' }}>{current.data?.name ?? '正在加载…'}</div><div style={{ fontSize: 11, color: 'var(--ws-sidebar-text)', marginTop: 1 }}>{current.data?.role ?? ''}</div></div>
          </div>
        </div>
      </aside>
      <main style={{ flex: 1, minWidth: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}><Outlet /></main>
    </div>
  )
}
