import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { NavLink, useNavigate } from 'react-router-dom'
import { AUTH_QUERY_KEY, logout, me } from '../api/auth'
import { Logo } from '../components/Logo'
import { errorMessage } from '../api/request'
import * as DropdownMenu from '@radix-ui/react-dropdown-menu'

interface NavItem {
  to: string
  label: string
  icon: () => React.ReactNode
  end?: boolean
}

const NAV_GROUPS: { label: string; items: NavItem[] }[] = [
  { label: '概览', items: [{ to: '/workspace', label: '总览', end: true, icon: () => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg> }] },
  { label: '分析', items: [
    { to: '/workspace/chat', label: '分析对话', icon: () => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg> },
    { to: '/workspace/scenarios', label: '场景库', icon: () => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M4 4h16v16H4z"/><path d="M8 8h8M8 12h8M8 16h5"/></svg> },
    { to: '/workspace/agents', label: '智能体广场', icon: () => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="12" cy="8" r="4"/><path d="M20 21a8 8 0 1 0-16 0"/><circle cx="12" cy="8" r="1" fill="currentColor"/></svg> },
    { to: '/workspace/skills', label: 'Skills 库', icon: () => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M12 2l2.4 4.86L20 7.67l-4 3.9.94 5.51L12 14.5l-4.94 2.58L8 11.57l-4-3.9 5.6-.81L12 2z"/><path d="M5 21h14"/></svg> },
    { to: '/workspace/mcp', label: 'MCP 库', icon: () => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/><path d="M10 6.5h4a3.5 3.5 0 0 1 3.5 3.5v4M14 17.5h-4A3.5 3.5 0 0 1 6.5 14v-4"/></svg> },
  ] },
  { label: '资源', items: [
    { to: '/workspace/data', label: '工作空间', icon: () => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg> },
    { to: '/workspace/my-scenarios', label: '我的场景', icon: () => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M3 5h18v14H3z"/><path d="M7 9h10M7 13h6"/></svg> },
    { to: '/workspace/my-agents', label: '我的智能体', icon: () => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg> },
    { to: '/workspace/my-skills', label: '我的 Skills', icon: () => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M12 2l2.4 4.86L20 7.67l-4 3.9.94 5.51L12 14.5l-4.94 2.58L8 11.57l-4-3.9 5.6-.81L12 2z"/><path d="M5 21h14"/></svg> },
  ] },
  { label: '系统', items: [{ to: '/workspace/settings', label: '设置', icon: () => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg> }] },
]

const ROLE_LABEL = { admin: '管理员', reviewer: '审核员', teacher: '教师', student: '学生' } as const

// **后台入口原来一处都没有。** admin 只靠登录那一跳进得去，点了「返回工作台」
// 就回不来；reviewer 连那一跳都没有，等于完全进不去。落点按角色分：
// reviewer 打不开用户管理那一页
const BACKEND_ENTRY = { admin: '/admin/users', reviewer: '/admin/agents' } as const

function NavItemRow({ item }: { item: NavItem }) {
  const [hovered, setHovered] = useState(false)
  return (
    <NavLink to={item.to} end={item.end} title={item.label} className="nav-row" onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)} style={({ isActive }) => ({ display: 'flex', alignItems: 'center', gap: 10, fontSize: 13, fontWeight: isActive ? 600 : 400, color: isActive ? 'var(--ws-sidebar-active)' : 'var(--ws-sidebar-text)', background: isActive ? 'var(--ws-sidebar-accent)' : hovered ? 'var(--ws-sidebar-hover)' : 'transparent', textDecoration: 'none', cursor: 'pointer', transition: 'background 0.15s, color 0.15s' })}>
      <span style={{ flexShrink: 0, display: 'grid', placeItems: 'center' }}>{item.icon()}</span><span className="nav-label">{item.label}</span>
    </NavLink>
  )
}

export function WorkspaceSidebar() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const current = useQuery({ queryKey: AUTH_QUERY_KEY, queryFn: () => me() })
  const [collapsed, setCollapsed] = useState(true)
  const logoutMutation = useMutation({
    mutationFn: logout,
    onSuccess() {
      queryClient.clear()
      navigate('/login', { replace: true })
    },
  })
  const user = current.data
  const backendTo = user && user.role in BACKEND_ENTRY ? BACKEND_ENTRY[user.role as keyof typeof BACKEND_ENTRY] : null

  return (
    <aside className={`ws-sidebar${collapsed ? ' collapsed' : ''}`} style={{ flexShrink: 0, background: 'var(--ws-sidebar-bg)', display: 'flex', flexDirection: 'column', height: '100vh', overflow: 'hidden' }}>
      <div className="ws-header">
        <Logo height={22} color="#fff" />
        <div className="ws-brand"><div style={{ fontSize: 14, fontWeight: 700, color: '#fff', lineHeight: 1.2 }}>FinAgentPlatform</div><div style={{ fontSize: 10, color: 'var(--ws-sidebar-text)', marginTop: 2 }}>工作台</div></div>
        <button type="button" className="ws-collapse" aria-label={collapsed ? '展开侧栏' : '折叠侧栏'} aria-expanded={!collapsed} onClick={() => setCollapsed(value => !value)}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points={collapsed ? '13 17 18 12 13 7' : '11 17 6 12 11 7'} /></svg>
        </button>
      </div>
      <nav style={{ flex: 1, overflowY: 'auto', padding: '8px 0 12px' }}>
        {NAV_GROUPS.map((group, index) => (
          <div key={group.label}>
            {index > 0 && <div style={{ height: 1, background: 'var(--ws-sidebar-border)', margin: '6px 16px' }} />}
            <div className="ws-group-label">{group.label}</div>
            {group.items.map(item => <NavItemRow key={item.to} item={item} />)}
          </div>
        ))}
        {backendTo && (
          <div>
            <div style={{ height: 1, background: 'var(--ws-sidebar-border)', margin: '6px 16px' }} />
            <div className="ws-group-label">管理</div>
            <NavItemRow item={{
              to: backendTo,
              label: '管理后台',
              icon: () => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M12 2 3 6v6c0 5 3.8 9.2 9 10 5.2-.8 9-5 9-10V6z"/><path d="m9 12 2 2 4-4"/></svg>,
            }} />
          </div>
        )}
      </nav>
      <div style={{ borderTop: '1px solid var(--ws-sidebar-border)' }}>
        <DropdownMenu.Root>
          <DropdownMenu.Trigger asChild>
            <button
              type="button"
              className="ws-userbar"
              aria-label={`用户菜单：${user?.name ?? '正在加载'}`}
              style={{ display: 'flex', alignItems: 'center', gap: 10, background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit', textAlign: 'left' }}
            >
              <div style={{ width: 30, height: 30, borderRadius: '50%', background: 'var(--action)', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, fontWeight: 700, flexShrink: 0 }}>{user?.name.at(0) ?? '·'}</div>
              <div className="ws-user-info" style={{ minWidth: 0, flex: 1 }}><div style={{ fontSize: 13, fontWeight: 600, color: '#fff', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{user?.name ?? '正在加载…'}</div><div style={{ fontSize: 11, color: 'var(--ws-sidebar-text)', marginTop: 1 }}>{user ? ROLE_LABEL[user.role] : ''}</div></div>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="ws-userbar-chevron" style={{ color: 'var(--ws-sidebar-text)' }} aria-hidden="true"><polyline points="18 15 12 9 6 15"/></svg>
            </button>
          </DropdownMenu.Trigger>
          <DropdownMenu.Portal>
            <DropdownMenu.Content className="theme-menu" align="start" side="top" sideOffset={6}>
              <DropdownMenu.Item className="theme-menu-item" onSelect={() => navigate('/')}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
                返回首页
              </DropdownMenu.Item>
              <DropdownMenu.Item className="theme-menu-item thread-menu-danger" disabled={logoutMutation.isPending} onSelect={() => logoutMutation.mutate()}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/></svg>
                {logoutMutation.isPending ? '正在退出…' : '退出登录'}
              </DropdownMenu.Item>
            </DropdownMenu.Content>
          </DropdownMenu.Portal>
        </DropdownMenu.Root>
        {logoutMutation.isError && <div role="alert" style={{ padding: '2px 16px 8px', color: '#FCA5A5', fontSize: 11 }}>{errorMessage(logoutMutation.error, '退出失败，请重试')}</div>}
      </div>
    </aside>
  )
}
