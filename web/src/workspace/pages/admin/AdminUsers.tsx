import { useState } from 'react'
import { AdminPageHeader, AdminTableSection } from './AdminUi'
import {
  approveButtonStyle,
  cellStyle,
  monoCellStyle,
  nameCellStyle,
  pageStyle,
  rejectButtonStyle,
  tableStyle,
  tagStyle,
  thStyle,
} from './AdminStyles'

type Role = 'teacher' | 'student' | 'admin'
type UserStatus = 'active' | 'disabled'

interface User {
  id: string; name: string; email: string; role: Role
  quota: number; status: UserStatus; createdAt: string
}

interface PendingUser {
  id: string; name: string; email: string; dept: string
  identity: '教师' | '学生'; appliedAt: string
}

interface EditModal { user: User; quota: number; role: Role }

const MOCK_USERS: User[] = [
  { id: '1', name: '张老师', email: 'zhang@fin.edu.cn', role: 'teacher', quota: 120, status: 'active', createdAt: '2026-01-15' },
  { id: '2', name: '李教授', email: 'li@fin.edu.cn', role: 'teacher', quota: 120, status: 'active', createdAt: '2026-01-20' },
  { id: '3', name: '赵同学', email: 'zhao@fin.edu.cn', role: 'student', quota: 40, status: 'active', createdAt: '2026-03-01' },
  { id: '4', name: '陈研究生', email: 'chen@fin.edu.cn', role: 'student', quota: 40, status: 'disabled', createdAt: '2026-03-05' },
  { id: '5', name: '管理员', email: 'admin@fin.edu.cn', role: 'admin', quota: 999, status: 'active', createdAt: '2025-12-01' },
]

const MOCK_PENDING: PendingUser[] = [
  { id: 'p1', name: '王明', email: 'wang@fin.edu.cn', dept: '金融学院', identity: '教师', appliedAt: '2026-08-09 09:21' },
  { id: 'p2', name: '陈小红', email: 'chenxh@fin.edu.cn', dept: '金融学院', identity: '学生', appliedAt: '2026-08-09 10:05' },
  { id: 'p3', name: '刘博', email: 'liu@fin.edu.cn', dept: '会计学院', identity: '学生', appliedAt: '2026-08-09 11:30' },
]

const ROLE_LABEL: Record<Role, string> = { teacher: '教师', student: '学生', admin: '管理员' }
const ROLE_STYLE: Record<Role, { bg: string; color: string }> = {
  teacher: { bg: '#EFF6FF', color: '#2563EB' },
  student: { bg: '#F5F3FF', color: '#7C3AED' },
  admin:   { bg: '#FEF2F2', color: '#DC2626' },
}

export function AdminUsers() {
  const [users, setUsers] = useState(MOCK_USERS)
  const [pending, setPending] = useState(MOCK_PENDING)
  const [search, setSearch] = useState('')
  const [roleFilter, setRoleFilter] = useState<'all' | Role>('all')
  const [statusFilter, setStatusFilter] = useState<'all' | UserStatus>('all')
  const [editModal, setEditModal] = useState<EditModal | null>(null)

  const filtered = users.filter(u => {
    const matchSearch = u.name.includes(search) || u.email.includes(search)
    const matchRole = roleFilter === 'all' || u.role === roleFilter
    const matchStatus = statusFilter === 'all' || u.status === statusFilter
    return matchSearch && matchRole && matchStatus
  })

  const handleToggleStatus = (id: string) => setUsers(prev => prev.map(u => u.id === id ? { ...u, status: u.status === 'active' ? 'disabled' as UserStatus : 'active' as UserStatus } : u))
  const handleSaveEdit = () => { if (!editModal) return; setUsers(prev => prev.map(u => u.id === editModal.user.id ? { ...u, role: editModal.role, quota: editModal.quota } : u)); setEditModal(null) }
  const handleApprove = (id: string, p: PendingUser) => {
    setUsers(prev => [{ id: `new-${id}`, name: p.name, email: p.email, role: p.identity === '教师' ? 'teacher' as Role : 'student' as Role, quota: p.identity === '教师' ? 120 : 40, status: 'active', createdAt: new Date().toISOString().split('T')[0] }, ...prev])
    setPending(prev => prev.filter(x => x.id !== id))
  }
  const handleReject = (id: string) => setPending(prev => prev.filter(x => x.id !== id))


  return (
    <div style={pageStyle}>
      <AdminPageHeader eyebrow="// USER MANAGEMENT" title="用户管理" pendingCount={pending.length} pendingLabel="个待处理" />

      <AdminTableSection title="待审核用户">
        {pending.length === 0 ? (
          <div style={{ padding: '48px 20px', textAlign: 'center', color: 'var(--text-muted)', fontSize: 13 }}>暂无待审核用户</div>
        ) : (
          <table style={tableStyle}>
            <thead><tr>{['申请人','邮箱','院系','身份','申请时间','操作'].map(h => <th key={h} style={thStyle}>{h}</th>)}</tr></thead>
            <tbody>
              {pending.map((p, i) => (
                <tr key={p.id} style={{ borderBottom: i < pending.length - 1 ? '1px solid var(--border-light)' : 'none' }}>
                  <td style={nameCellStyle}>{p.name}</td>
                  <td style={cellStyle}>{p.email}</td>
                  <td style={cellStyle}>{p.dept}</td>
                  <td style={cellStyle}><span style={tagStyle}>{p.identity}</span></td>
                  <td style={monoCellStyle}>{p.appliedAt}</td>
                  <td style={cellStyle}>
                    <div style={{ display: 'flex', gap: 8 }}>
                      <button type="button" onClick={() => handleApprove(p.id, p)} style={approveButtonStyle}>激活</button>
                      <button type="button" onClick={() => handleReject(p.id)} style={rejectButtonStyle}>拒绝</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </AdminTableSection>

      <div style={{ display: 'flex', gap: 10, marginBottom: 14, flexWrap: 'wrap' as const }}>
        <input value={search} onChange={e => setSearch(e.target.value)} placeholder="搜索姓名或邮箱" style={{ padding: '7px 12px', border: '1px solid var(--border)', borderRadius: 6, fontSize: 13, fontFamily: 'inherit', outline: 'none', background: 'var(--surface)', color: 'var(--text-primary)', width: 200 }} />
        <select value={roleFilter} onChange={e => setRoleFilter(e.target.value as 'all' | Role)} style={{ padding: '7px 12px', border: '1px solid var(--border)', borderRadius: 6, fontSize: 13, fontFamily: 'inherit', background: 'var(--surface)', color: 'var(--text-secondary)', cursor: 'pointer' }}>
          <option value="all">全部角色</option><option value="teacher">教师</option><option value="student">学生</option><option value="admin">管理员</option>
        </select>
        <select value={statusFilter} onChange={e => setStatusFilter(e.target.value as 'all' | UserStatus)} style={{ padding: '7px 12px', border: '1px solid var(--border)', borderRadius: 6, fontSize: 13, fontFamily: 'inherit', background: 'var(--surface)', color: 'var(--text-secondary)', cursor: 'pointer' }}>
          <option value="all">全部状态</option><option value="active">正常</option><option value="disabled">已禁用</option>
        </select>
      </div>
      <AdminTableSection
        title="全部用户"
        action={<button type="button" style={approveButtonStyle}>+ 创建账号</button>}
      >
        <table style={tableStyle}>
          <thead><tr>{['姓名','邮箱','角色','配额（月）','状态','注册时间','操作'].map(h => <th key={h} style={thStyle}>{h}</th>)}</tr></thead>
          <tbody>
            {filtered.map((user, i) => {
              const rs = ROLE_STYLE[user.role]
              return (
                <tr key={user.id} style={{ borderBottom: i < filtered.length - 1 ? '1px solid var(--border-light)' : 'none', opacity: user.status === 'disabled' ? 0.6 : 1 }}>
                  <td style={{ padding: '12px 16px', fontWeight: 500, color: 'var(--text-primary)' }}>{user.name}</td>
                  <td style={{ padding: '12px 16px', color: 'var(--text-secondary)', fontSize: 12 }}>{user.email}</td>
                  <td style={{ padding: '12px 16px' }}><span style={{ padding: '2px 8px', borderRadius: 4, fontSize: 11, fontWeight: 600, background: rs.bg, color: rs.color }}>{ROLE_LABEL[user.role]}</span></td>
                  <td style={{ padding: '12px 16px', fontSize: 12, fontFamily: "'JetBrains Mono', monospace", color: 'var(--text-secondary)' }}>{user.quota}K tokens</td>
                  <td style={{ padding: '12px 16px' }}><span style={{ fontSize: 12, fontWeight: 600, color: user.status === 'active' ? 'var(--status-done)' : 'var(--text-muted)' }}>{user.status === 'active' ? '● 正常' : '○ 已禁用'}</span></td>
                  <td style={{ padding: '12px 16px', fontSize: 12, color: 'var(--text-muted)' }}>{user.createdAt}</td>
                  <td style={{ padding: '12px 16px' }}>
                    <div style={{ display: 'flex', gap: 6 }}>
                      <button onClick={() => setEditModal({ user, quota: user.quota, role: user.role })} style={{ padding: '4px 10px', background: 'transparent', color: 'var(--action)', border: '1px solid var(--action-border)', borderRadius: 5, fontSize: 11, cursor: 'pointer', fontFamily: 'inherit' }}>编辑</button>
                      {user.role !== 'admin' && <button onClick={() => handleToggleStatus(user.id)} style={{ padding: '4px 10px', background: 'transparent', color: user.status === 'active' ? '#DC2626' : 'var(--status-done)', border: '1px solid ' + (user.status === 'active' ? '#FECACA' : '#A7F3D0'), borderRadius: 5, fontSize: 11, cursor: 'pointer', fontFamily: 'inherit' }}>{user.status === 'active' ? '禁用' : '启用'}</button>}
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </AdminTableSection>

      {/* 编辑弹窗 */}
      {editModal && (
        <>
          <div onClick={() => setEditModal(null)} style={{ position: 'fixed', inset: 0, background: 'rgba(13,24,41,0.4)', backdropFilter: 'blur(4px)', zIndex: 200 }} />
          <div style={{ position: 'fixed', top: '50%', left: '50%', transform: 'translate(-50%,-50%)', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12, padding: 32, width: 400, zIndex: 201, boxShadow: '0 20px 60px rgba(11,46,92,0.2)' }}>
            <div style={{ fontSize: 17, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 24 }}>编辑用户：{editModal.user.name}</div>
            <div style={{ marginBottom: 16 }}>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 500, color: 'var(--text-muted)', marginBottom: 6, textTransform: 'uppercase' as const, letterSpacing: '0.1em' }}>角色</label>
              <select value={editModal.role} onChange={e => setEditModal({ ...editModal, role: e.target.value as Role })} style={{ width: '100%', padding: '9px 12px', border: '1px solid var(--border)', borderRadius: 7, fontSize: 13, fontFamily: 'inherit', background: 'var(--surface)', color: 'var(--text-primary)', outline: 'none' }}>
                <option value="teacher">教师</option><option value="student">学生</option><option value="admin">管理员</option>
              </select>
            </div>
            <div style={{ marginBottom: 24 }}>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 500, color: 'var(--text-muted)', marginBottom: 6, textTransform: 'uppercase' as const, letterSpacing: '0.1em' }}>月 Token 配额（K）</label>
              <input type="number" value={editModal.quota} onChange={e => setEditModal({ ...editModal, quota: Number(e.target.value) })} style={{ width: '100%', padding: '9px 12px', border: '1px solid var(--border)', borderRadius: 7, fontSize: 13, fontFamily: 'inherit', background: 'var(--surface)', color: 'var(--text-primary)', outline: 'none', boxSizing: 'border-box' as const }} />
            </div>
            <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
              <button onClick={() => setEditModal(null)} style={{ padding: '8px 18px', background: 'var(--surface)', color: 'var(--text-secondary)', border: '1px solid var(--border)', borderRadius: 7, fontSize: 13, cursor: 'pointer', fontFamily: 'inherit' }}>取消</button>
              <button onClick={handleSaveEdit} style={{ padding: '8px 18px', background: 'var(--action)', color: '#fff', border: 'none', borderRadius: 7, fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>保存</button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
