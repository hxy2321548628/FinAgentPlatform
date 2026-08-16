import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { NavLink, useNavigate } from 'react-router-dom'
import { AUTH_QUERY_KEY, logout, me } from '../api/auth'
import { errorMessage } from '../api/request'

const LOGO_PATH_1 = 'M24.22,27.73l1.05-2c.36-.69.73-1.38,1.08-2.07a.26.26,0,0,1,.27-.17h3.83a.26.26,0,0,1,.27.18c1.44,3.06,3,6.08,4.65,9a.23.23,0,0,0,.08.16H27.09a.3.3,0,0,1-.32-.19q-1.2-2.34-2.42-4.66l-.14-.25c-.05.09-.1.16-.13.23l-2.44,4.7a.25.25,0,0,1-.26.17H13l.4-.83c1.53-2.72,2.94-5.5,4.27-8.33a.35.35,0,0,1,.38-.24h3.74a.27.27,0,0,1,.28.18l2,3.84Z'
const LOGO_PATH_2 = 'M24.21,4.19a82.908,82.908,0,0,0,2.43,9.16,85.1,85.1,0,0,0,3.43,8.85H18.33a79,79,0,0,0,3.47-8.86,84.311,84.311,0,0,0,2.41-9.15Zm0,16.18A1.3,1.3,0,1,0,23,19.07a1.26,1.26,0,0,0,1.23,1.3Z'

interface NavItem {
  to: string
  label: string
  icon: () => React.ReactNode
  end?: boolean
}

const NAV_GROUPS: { items: NavItem[] }[] = [
  { items: [{ to: '/workspace', label: '总览', end: true, icon: () => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg> }] },
  { items: [{ to: '/workspace/chat', label: '分析对话', icon: () => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg> }] },
  { items: [
    { to: '/workspace/scenarios', label: '场景库', icon: () => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M4 4h16v16H4z"/><path d="M8 8h8M8 12h8M8 16h5"/></svg> },
    { to: '/workspace/agents', label: '智能体广场', icon: () => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="12" cy="8" r="4"/><path d="M20 21a8 8 0 1 0-16 0"/><circle cx="12" cy="8" r="1" fill="currentColor"/></svg> },
    { to: '/workspace/skills', label: 'Skills 库', icon: () => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M12 2l2.4 4.86L20 7.67l-4 3.9.94 5.51L12 14.5l-4.94 2.58L8 11.57l-4-3.9 5.6-.81L12 2z"/><path d="M5 21h14"/></svg> },
    { to: '/workspace/mcp', label: 'MCP 库', icon: () => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/><path d="M10 6.5h4a3.5 3.5 0 0 1 3.5 3.5v4M14 17.5h-4A3.5 3.5 0 0 1 6.5 14v-4"/></svg> },
  ] },
  { items: [
    { to: '/workspace/data', label: '工作空间', icon: () => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg> },
    { to: '/workspace/my-scenarios', label: '我的场景', icon: () => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M3 5h18v14H3z"/><path d="M7 9h10M7 13h6"/></svg> },
    { to: '/workspace/my-agents', label: '我的智能体', icon: () => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg> },
    { to: '/workspace/my-skills', label: '我的 Skills', icon: () => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M12 2l2.4 4.86L20 7.67l-4 3.9.94 5.51L12 14.5l-4.94 2.58L8 11.57l-4-3.9 5.6-.81L12 2z"/><path d="M5 21h14"/></svg> },
  ] },
  { items: [{ to: '/workspace/settings', label: '设置', icon: () => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg> }] },
]

const ROLE_LABEL = { admin: '管理员', reviewer: '审核员', teacher: '教师', student: '学生' } as const

function NavItemRow({ item }: { item: NavItem }) {
  return (
    <NavLink to={item.to} end={item.end} style={({ isActive }) => ({ display: 'flex', alignItems: 'center', gap: 10, padding: '9px 16px', fontSize: 13, fontWeight: isActive ? 600 : 400, color: isActive ? 'var(--ws-sidebar-active)' : 'var(--ws-sidebar-text)', background: isActive ? 'var(--ws-sidebar-accent)' : 'transparent', borderLeft: isActive ? '3px solid var(--action)' : '3px solid transparent', textDecoration: 'none', cursor: 'pointer', transition: 'background 0.15s, color 0.15s' })}>
      <span style={{ flexShrink: 0 }}>{item.icon()}</span>{item.label}
    </NavLink>
  )
}

export function WorkspaceSidebar() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const current = useQuery({ queryKey: AUTH_QUERY_KEY, queryFn: () => me() })
  const [userMenuOpen, setUserMenuOpen] = useState(false)
  const logoutMutation = useMutation({
    mutationFn: logout,
    onSuccess() {
      queryClient.clear()
      navigate('/login', { replace: true })
    },
  })
  const user = current.data

  return (
    <aside style={{ width: 220, flexShrink: 0, background: 'var(--ws-sidebar-bg)', display: 'flex', flexDirection: 'column', height: '100vh', overflow: 'hidden' }}>
      <div style={{ height: 72, display: 'flex', alignItems: 'center', gap: 9, padding: '0 16px', borderBottom: '1px solid var(--ws-sidebar-border)', flexShrink: 0 }}>
        <svg viewBox="12 3 24 34" fill="currentColor" style={{ height: 22, width: 'auto', color: '#0E8A7B' }} aria-hidden="true"><path d={LOGO_PATH_1}/><path d={LOGO_PATH_2}/></svg>
        <div><div style={{ fontSize: 14, fontWeight: 700, color: '#fff', lineHeight: 1.2 }}>FinAgentPlatform</div><div style={{ fontSize: 10, color: 'var(--ws-sidebar-text)', marginTop: 2 }}>工作台</div></div>
      </div>
      <nav style={{ flex: 1, overflowY: 'auto', padding: '10px 0' }}>
        {NAV_GROUPS.map((group, index) => <div key={index}>{index > 0 && <div style={{ height: 1, background: 'var(--ws-sidebar-border)', margin: '6px 0' }}/>} {group.items.map(item => <NavItemRow key={item.to} item={item}/>)}</div>)}
      </nav>
      <div style={{ borderTop: '1px solid var(--ws-sidebar-border)' }}>
        {userMenuOpen && (
          <div style={{ padding: '8px 0', borderBottom: '1px solid var(--ws-sidebar-border)' }}>
            <button onClick={() => { setUserMenuOpen(false); navigate('/') }} style={userMenuItemStyle}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
              返回首页
            </button>
            <button onClick={() => logoutMutation.mutate()} disabled={logoutMutation.isPending} style={{ ...userMenuItemStyle, color: logoutMutation.isPending ? 'var(--ws-sidebar-text)' : '#FCA5A5' }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/></svg>
              {logoutMutation.isPending ? '正在退出…' : '退出登录'}
            </button>
            {logoutMutation.isError && <div role="alert" style={{ padding: '4px 16px 0', color: '#FCA5A5', fontSize: 11 }}>{errorMessage(logoutMutation.error, '退出失败，请重试')}</div>}
          </div>
        )}
        <button
          type="button"
          aria-expanded={userMenuOpen}
          onClick={() => setUserMenuOpen(open => !open)}
          style={{ width: '100%', padding: '12px 16px', display: 'flex', alignItems: 'center', gap: 10, background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit', textAlign: 'left' }}
        >
          <div style={{ width: 32, height: 32, borderRadius: '50%', background: 'var(--action)', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, fontWeight: 700, flexShrink: 0 }}>{user?.name.at(0) ?? '·'}</div>
          <div style={{ minWidth: 0, flex: 1 }}><div style={{ fontSize: 13, fontWeight: 600, color: '#fff', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{user?.name ?? '正在加载…'}</div><div style={{ fontSize: 11, color: 'var(--ws-sidebar-text)', marginTop: 1 }}>{user ? ROLE_LABEL[user.role] : ''}</div></div>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" style={{ color: 'var(--ws-sidebar-text)', transform: userMenuOpen ? 'rotate(180deg)' : 'none', transition: 'transform 0.15s' }}><polyline points="18 15 12 9 6 15"/></svg>
        </button>
      </div>
    </aside>
  )
}

const userMenuItemStyle: React.CSSProperties = {
  display: 'flex', alignItems: 'center', gap: 10, width: '100%', padding: '9px 16px',
  fontSize: 13, color: 'var(--ws-sidebar-text)', background: 'none', border: 'none',
  cursor: 'pointer', fontFamily: 'inherit', textAlign: 'left',
}
