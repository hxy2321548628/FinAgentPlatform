import { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Activity, ArrowLeft, Bot, ChartNoAxesColumnIncreasing, Network, Users, Wrench } from 'lucide-react'
import { AUTH_QUERY_KEY, me } from '../../../api/auth'
import { Logo } from '../../../components/Logo'

const ROLE_LABEL = { admin: '管理员', reviewer: '审核员', teacher: '教师', student: '学生' } as const

const ADMIN_GROUPS = [
  {
    label: '账号与权限',
    shortLabel: '账号',
    links: [
      { to: '/admin/users', label: '用户管理', icon: Users },
    ],
  },
  {
    label: '内容与能力',
    shortLabel: '内容',
    links: [
      // **场景与智能体共用这一个审核入口**：它们在库里是同一张表，
      // 区别只是「挂没挂子智能体」（P6-decision G2）。原来那个「场景管理」页
      // 审的是同一个队列，两个入口只会让两边状态看起来不一致
      { to: '/admin/agents', label: '场景与智能体审核', icon: Bot },
      { to: '/admin/skills', label: 'Skill 审核', icon: Wrench },
      { to: '/admin/mcp', label: 'MCP 管理', icon: Network },
    ],
  },
  {
    label: '运营与系统',
    shortLabel: '系统',
    links: [
      { to: '/admin/usage', label: '用量看板', icon: ChartNoAxesColumnIncreasing },
      { to: '/admin/system', label: '系统状态', icon: Activity },
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
    <div className="admin-shell">
      <a className="skip-link" href="#admin-main">跳到主要内容</a>
      <aside className={`ws-sidebar admin-sidebar${collapsed ? ' collapsed' : ''}`}>
        <div className="ws-sidebar-content">
          <div className="ws-header">
            <Logo height={22} color="#fff" />
            <div className="ws-brand"><div className="admin-brand-title">FinAgentPlatform</div><div className="admin-brand-subtitle">管理后台</div></div>
          </div>

          <nav className="ws-nav" aria-label="后台导航">
            {visible.map((group, index) => (
              <div key={group.label}>
                {index > 0 && <div className="ws-nav-divider" />}
                <div className="ws-group-label">
                  <span className="admin-group-label-full">{group.label}</span>
                  <span className="admin-group-label-short">{group.shortLabel}</span>
                </div>
                {group.links.map(link => {
                  const Icon = link.icon
                  return (
                    <NavLink
                      key={link.to}
                      to={link.to}
                      aria-label={link.label}
                      title={link.label}
                      className={({ isActive }) => `nav-row admin-nav-row${isActive ? ' active' : ''}`}
                    >
                      <span className="nav-icon"><Icon size={17} strokeWidth={1.7} aria-hidden="true" /></span>
                      <span className="nav-label">{link.label}</span>
                    </NavLink>
                  )
                })}
              </div>
            ))}
          </nav>

          <div className="ws-sidebar-footer">
            <div className="ws-sidebar-actions">
              <NavLink to="/workspace" className="ws-sidebar-action" aria-label="返回工作台" title="返回工作台">
                <span className="ws-sidebar-action-icon"><ArrowLeft size={17} strokeWidth={1.7} aria-hidden="true" /></span>
                <span className="ws-menu-label">返回工作台</span>
              </NavLink>
            </div>
            <div className="ws-userbar admin-userbar" aria-label={`当前用户：${current.data?.name ?? '正在加载'}`}>
              <div className="admin-user-avatar">{current.data?.name.at(0) ?? '·'}</div>
              <div className="ws-user-info admin-user-info"><div className="admin-user-name">{current.data?.name ?? '正在加载…'}</div><div className="admin-user-role">{current.data ? ROLE_LABEL[current.data.role] : ''}</div></div>
            </div>
          </div>
        </div>
        <button type="button" className="ws-collapse" aria-label={collapsed ? '展开侧栏' : '折叠侧栏'} aria-expanded={!collapsed} onClick={() => setCollapsed(value => !value)}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points={collapsed ? '13 17 18 12 13 7' : '11 17 6 12 11 7'} /></svg>
        </button>
      </aside>
      <main id="admin-main" className="admin-main page-grid-surface" tabIndex={-1}><Outlet /></main>
    </div>
  )
}
