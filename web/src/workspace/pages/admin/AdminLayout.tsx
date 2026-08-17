import { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { AUTH_QUERY_KEY, me } from '../../../api/auth'
import { Logo } from '../../../components/Logo'

const ROLE_LABEL = { admin: '管理员', reviewer: '审核员', teacher: '教师', student: '学生' } as const

const ADMIN_GROUPS = [
  {
    label: '账号与权限',
    shortLabel: '账号',
    links: [
      { to: '/admin/users', label: '用户管理', icon: <><circle cx="9" cy="7" r="4"/><path d="M17 11a4 4 0 1 0 0-8M2 21a7 7 0 0 1 14 0M16 14a6 6 0 0 1 6 6"/></> },
    ],
  },
  {
    label: '内容与能力',
    shortLabel: '内容',
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
    shortLabel: '系统',
    links: [
      { to: '/admin/usage', label: '用量看板', icon: <><path d="M3 3v18h18"/><path d="m7 16 4-5 4 3 5-7"/></> },
      { to: '/admin/system', label: '系统状态', icon: <><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06M19.4 9a1.65 1.65 0 0 1 .33-1.82l.06-.06M15 4.6a1.65 1.65 0 0 0 1-1.51V3M9 4.6a1.65 1.65 0 0 1-1-1.51V3M4.6 9a1.65 1.65 0 0 0-1.51-1H3M4.6 15a1.65 1.65 0 0 1-1.51 1H3M9 19.4a1.65 1.65 0 0 0-1 1.51V21M15 19.4a1.65 1.65 0 0 1 1 1.51V21"/></> },
    ],
  },
]

export function AdminLayout() {
  const current = useQuery({ queryKey: AUTH_QUERY_KEY, queryFn: () => me() })
  const [collapsed, setCollapsed] = useState(true)
  // reviewer 看得到三个审核入口（agent / skill / MCP）；账号、用量、系统仍只属于 admin。
  // MCP 那一页对 reviewer 只显示批与拒，启停与探活是运维动作，见页面内的判断
  const reviewerOnly = current.data?.role === 'reviewer'
  const visible = reviewerOnly
    ? ADMIN_GROUPS.map(group => ({ ...group, links: group.links.filter(link => ['/admin/agents', '/admin/skills', '/admin/mcp'].includes(link.to)) })).filter(
        group => group.links.length > 0,
      )
    : ADMIN_GROUPS

  return (
    <div className="admin-shell" style={{ display: 'flex', height: '100vh', overflow: 'hidden', background: 'var(--bg)' }}>
      <a className="skip-link" href="#admin-main">跳到主要内容</a>
      <aside className={`ws-sidebar admin-sidebar${collapsed ? ' collapsed' : ''}`} style={{ flexShrink: 0, height: '100vh' }}>
        <div className="ws-sidebar-content">
          <div className="ws-header">
            <Logo height={22} color="#fff" />
            <div className="ws-brand"><div style={{ fontSize: 14, fontWeight: 700, color: '#fff', lineHeight: 1.2 }}>FinAgentPlatform</div><div style={{ fontSize: 10, color: 'var(--ws-sidebar-text)', marginTop: 2 }}>管理后台</div></div>
          </div>

          <nav className="ws-nav">
            {visible.map((group, index) => (
              <div key={group.label}>
                {index > 0 && <div className="ws-nav-divider" />}
                <div className="ws-group-label">
                  <span className="admin-group-label-full">{group.label}</span>
                  <span className="admin-group-label-short">{group.shortLabel}</span>
                </div>
                {group.links.map(link => (
                  <NavLink
                    key={link.to}
                    to={link.to}
                    aria-label={link.label}
                    title={link.label}
                    className={({ isActive }) => `nav-row admin-nav-row${isActive ? ' active' : ''}`}
                  >
                    <span className="nav-icon"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">{link.icon}</svg></span>
                    <span className="nav-label">{link.label}</span>
                  </NavLink>
                ))}
              </div>
            ))}
          </nav>

          <div className="ws-sidebar-footer">
            <div className="ws-sidebar-actions">
              <NavLink to="/workspace" className="ws-sidebar-action" aria-label="返回工作台" title="返回工作台">
                <span className="ws-sidebar-action-icon"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path d="M19 12H5M12 19l-7-7 7-7"/></svg></span>
                <span className="ws-menu-label">返回工作台</span>
              </NavLink>
            </div>
            <div className="ws-userbar" aria-label={`当前用户：${current.data?.name ?? '正在加载'}`} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <div style={{ width: 30, height: 30, borderRadius: '50%', background: 'var(--action)', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, fontWeight: 700, flexShrink: 0 }}>{current.data?.name.at(0) ?? '·'}</div>
              <div className="ws-user-info" style={{ minWidth: 0, flex: 1 }}><div style={{ fontSize: 13, fontWeight: 600, color: '#fff', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{current.data?.name ?? '正在加载…'}</div><div style={{ fontSize: 11, color: 'var(--ws-sidebar-text)', marginTop: 1 }}>{current.data ? ROLE_LABEL[current.data.role] : ''}</div></div>
            </div>
          </div>
        </div>
        <button type="button" className="ws-collapse" aria-label={collapsed ? '展开侧栏' : '折叠侧栏'} aria-expanded={!collapsed} onClick={() => setCollapsed(value => !value)}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points={collapsed ? '13 17 18 12 13 7' : '11 17 6 12 11 7'} /></svg>
        </button>
      </aside>
      <main id="admin-main" tabIndex={-1} style={{ flex: 1, minWidth: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}><Outlet /></main>
    </div>
  )
}
