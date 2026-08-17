import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { adminKeys, createUser, listUsers, updateUser } from '../../../api/admin'
import { errorMessage } from '../../../api/request'
import type { AdminUser, UserRole } from '../../../api/types'
import { AdminPageHeader, AdminTableSection } from './AdminUi'
import * as DialogPrimitive from '@radix-ui/react-dialog'
import { Button } from '../../../components/ui/Button'
import {
  approveButtonStyle,
  cellStyle,
  monoCellStyle,
  nameCellStyle,
  pageStyle,
  tableStyle,
  thStyle,
} from './AdminStyles'

interface EditModal {
  user: AdminUser
  role: UserRole
  // 空串表示「跟着角色的默认档走」。**它与 0 是两回事** —— 0 是「一个 token 都不给」
  quota: string
  dept: string
}

const ROLE_LABEL: Record<UserRole, string> = {
  teacher: '教师',
  student: '学生',
  admin: '管理员',
  reviewer: '审核员',
}

const ROLE_STYLE: Record<UserRole, { bg: string; color: string }> = {
  teacher: { bg: '#EFF6FF', color: '#2563EB' },
  student: { bg: '#F5F3FF', color: '#7C3AED' },
  admin: { bg: '#FEF2F2', color: '#DC2626' },
  reviewer: { bg: '#FFF7ED', color: '#EA580C' },
}

const CREATABLE_ROLE: UserRole[] = ['teacher', 'student', 'reviewer', 'admin']

export function AdminUsers() {
  const queryClient = useQueryClient()
  const users = useQuery({ queryKey: adminKeys.users(), queryFn: listUsers })
  const [search, setSearch] = useState('')
  const [roleFilter, setRoleFilter] = useState<'all' | UserRole>('all')
  const [statusFilter, setStatusFilter] = useState<'all' | 'active' | 'disabled'>('all')
  const [editModal, setEditModal] = useState<EditModal | null>(null)
  const [creating, setCreating] = useState(false)
  const [failure, setFailure] = useState('')

  const refresh = () => queryClient.invalidateQueries({ queryKey: adminKeys.users() })

  const change = useMutation({
    mutationFn: (input: { id: string; body: Parameters<typeof updateUser>[1] }) =>
      updateUser(input.id, input.body),
    onSuccess: () => { setFailure(''); void refresh() },
    onError: (reason) => setFailure(errorMessage(reason, '保存失败')),
  })

  const all = users.data ?? []
  // **等激活的排最前** —— 管理员打开这一页的头等大事就是它
  const pending = all.filter(one => !one.is_active)
  const filtered = all.filter(one => {
    const matchSearch = one.name.includes(search) || one.email.includes(search)
    const matchRole = roleFilter === 'all' || one.role === roleFilter
    const matchStatus =
      statusFilter === 'all' || (statusFilter === 'active' ? one.is_active : !one.is_active)
    return matchSearch && matchRole && matchStatus
  })

  const saveEdit = () => {
    if (!editModal) return
    const trimmed = editModal.quota.trim()
    change.mutate({
      id: editModal.user.id,
      body: {
        role: editModal.role,
        dept: editModal.dept,
        // **空串要传 null，不是不传** —— 传 null 才是「清回默认档」，
        // 不传是「这一项不动」，两者在后端是两件事
        quota_tokens_daily: trimmed === '' ? null : Number(trimmed),
      },
    })
    setEditModal(null)
  }

  return (
    <div style={pageStyle}>
      <AdminPageHeader eyebrow="// USER MANAGEMENT" title="用户管理" pendingCount={pending.length} pendingLabel="个待处理" />

      {users.isError && <div role="alert" style={alertStyle}>{errorMessage(users.error)}</div>}
      {failure && <div role="alert" style={alertStyle}>{failure}</div>}

      <AdminTableSection title="待激活账号">
        {users.isPending ? (
          <div style={emptyStyle}>正在加载…</div>
        ) : pending.length === 0 ? (
          <div style={emptyStyle}>暂无待激活账号</div>
        ) : (
          <table style={tableStyle}>
            <thead><tr>{['用户名', '邮箱', '院系', '角色', '操作'].map(h => <th key={h} style={thStyle}>{h}</th>)}</tr></thead>
            <tbody>
              {pending.map((one, i) => (
                <tr key={one.id} style={{ borderBottom: i < pending.length - 1 ? '1px solid var(--border-light)' : 'none' }}>
                  <td style={nameCellStyle}>{one.name}</td>
                  <td style={cellStyle}>{one.email}</td>
                  <td style={cellStyle}>{one.dept || '—'}</td>
                  <td style={cellStyle}>{ROLE_LABEL[one.role]}</td>
                  <td style={cellStyle}>
                    <button
                      type="button"
                      disabled={change.isPending}
                      onClick={() => change.mutate({ id: one.id, body: { is_active: true } })}
                      style={approveButtonStyle}
                    >
                      激活
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </AdminTableSection>

      <div style={{ display: 'flex', gap: 10, marginBottom: 14, flexWrap: 'wrap' as const }}>
        <input value={search} onChange={e => setSearch(e.target.value)} placeholder="搜索用户名或邮箱" style={{ padding: '7px 12px', border: '1px solid var(--border)', borderRadius: 6, fontSize: 13, fontFamily: 'inherit', background: 'var(--surface)', color: 'var(--text-primary)', width: 200 }} />
        <select value={roleFilter} onChange={e => setRoleFilter(e.target.value as 'all' | UserRole)} style={selectStyle}>
          <option value="all">全部角色</option>
          {CREATABLE_ROLE.map(role => <option key={role} value={role}>{ROLE_LABEL[role]}</option>)}
        </select>
        <select value={statusFilter} onChange={e => setStatusFilter(e.target.value as 'all' | 'active' | 'disabled')} style={selectStyle}>
          <option value="all">全部状态</option><option value="active">正常</option><option value="disabled">未启用</option>
        </select>
      </div>

      <AdminTableSection
        title="全部账号"
        action={<button type="button" onClick={() => setCreating(true)} style={approveButtonStyle}>+ 创建账号</button>}
      >
        {users.isPending ? (
          <div style={emptyStyle}>正在加载…</div>
        ) : (
          <table style={tableStyle}>
            <thead><tr>{['用户名', '邮箱', '院系', '角色', '日配额', '状态', '操作'].map(h => <th key={h} style={thStyle}>{h}</th>)}</tr></thead>
            <tbody>
              {filtered.map((user, i) => {
                const rs = ROLE_STYLE[user.role]
                return (
                  <tr key={user.id} style={{ borderBottom: i < filtered.length - 1 ? '1px solid var(--border-light)' : 'none', opacity: user.is_active ? 1 : 0.6 }}>
                    <td style={nameCellStyle}>{user.name}</td>
                    <td style={{ ...cellStyle, fontSize: 12, whiteSpace: 'nowrap' }}>{user.email}</td>
                    <td style={cellStyle}>{user.dept || '—'}</td>
                    <td style={cellStyle}><span style={{ padding: '2px 8px', borderRadius: 4, fontSize: 11, fontWeight: 600, whiteSpace: 'nowrap', background: rs.bg, color: rs.color }}>{ROLE_LABEL[user.role]}</span></td>
                    {/* 留空表示走角色默认档，显示成「默认」而不是 0 —— 后者读起来像「不给配额」 */}
                    <td style={monoCellStyle}>{user.quota_tokens_daily === null ? '默认' : user.quota_tokens_daily.toLocaleString()}</td>
                    <td style={cellStyle}><span style={{ fontSize: 12, fontWeight: 600, whiteSpace: 'nowrap', color: user.is_active ? 'var(--status-done)' : 'var(--text-muted)' }}>{user.is_active ? '● 正常' : '○ 未启用'}</span></td>
                    <td style={cellStyle}>
                      <div style={{ display: 'flex', gap: 6 }}>
                        <button
                          onClick={() => setEditModal({
                            user,
                            role: user.role,
                            quota: user.quota_tokens_daily === null ? '' : String(user.quota_tokens_daily),
                            dept: user.dept,
                          })}
                          style={{ padding: '4px 10px', background: 'transparent', color: 'var(--action)', border: '1px solid var(--action-border)', borderRadius: 5, fontSize: 11, cursor: 'pointer', fontFamily: 'inherit', whiteSpace: 'nowrap' }}
                        >
                          编辑
                        </button>
                        <button
                          disabled={change.isPending}
                          onClick={() => change.mutate({ id: user.id, body: { is_active: !user.is_active } })}
                          style={{ padding: '4px 10px', background: 'transparent', color: user.is_active ? 'var(--danger)' : 'var(--status-done)', border: '1px solid ' + (user.is_active ? 'var(--danger-border)' : '#A7F3D0'), borderRadius: 5, fontSize: 11, cursor: 'pointer', fontFamily: 'inherit', whiteSpace: 'nowrap' }}
                        >
                          {user.is_active ? '停用' : '启用'}
                        </button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </AdminTableSection>

      {editModal && (
        <Modal title={`编辑账号：${editModal.user.name}`} onClose={() => setEditModal(null)} onSubmit={saveEdit}>
          <Labelled label="角色">
            <select value={editModal.role} onChange={e => setEditModal({ ...editModal, role: e.target.value as UserRole })} style={modalInputStyle}>
              {CREATABLE_ROLE.map(role => <option key={role} value={role}>{ROLE_LABEL[role]}</option>)}
            </select>
          </Labelled>
          <Labelled label="院系">
            <input value={editModal.dept} onChange={e => setEditModal({ ...editModal, dept: e.target.value })} style={modalInputStyle} />
          </Labelled>
          <Labelled label="每日 Token 配额（留空＝跟随角色默认档）">
            <input type="number" min={0} value={editModal.quota} placeholder="默认" onChange={e => setEditModal({ ...editModal, quota: e.target.value })} style={modalInputStyle} />
          </Labelled>
        </Modal>
      )}

      {creating && (
        <CreateUserModal
          onClose={() => setCreating(false)}
          onDone={() => { setCreating(false); void refresh() }}
          onError={setFailure}
        />
      )}
    </div>
  )
}

function CreateUserModal({ onClose, onDone, onError }: { onClose: () => void; onDone: () => void; onError: (message: string) => void }) {
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [dept, setDept] = useState('')
  const [role, setRole] = useState<UserRole>('teacher')

  const ready = Boolean(name.trim()) && /^[^@\s]+@[^@\s]+$/.test(email.trim()) && password.length >= 8

  const create = useMutation({
    mutationFn: () => createUser({ name: name.trim(), email: email.trim(), password, role, dept: dept.trim() }),
    onSuccess: onDone,
    onError: (reason) => onError(errorMessage(reason, '创建失败')),
  })

  return (
    <Modal title="创建账号" onClose={onClose} onSubmit={() => ready && create.mutate()} submitDisabled={!ready || create.isPending}>
      <Labelled label="用户名"><input value={name} onChange={e => setName(e.target.value)} style={modalInputStyle} /></Labelled>
      <Labelled label="邮箱（登录认它也认用户名）"><input type="email" value={email} onChange={e => setEmail(e.target.value)} style={modalInputStyle} /></Labelled>
      <Labelled label="初始口令（至少 8 位）"><input type="password" value={password} onChange={e => setPassword(e.target.value)} style={modalInputStyle} /></Labelled>
      <Labelled label="院系"><input value={dept} onChange={e => setDept(e.target.value)} style={modalInputStyle} /></Labelled>
      <Labelled label="角色">
        <select value={role} onChange={e => setRole(e.target.value as UserRole)} style={modalInputStyle}>
          {CREATABLE_ROLE.map(one => <option key={one} value={one}>{ROLE_LABEL[one]}</option>)}
        </select>
      </Labelled>
    </Modal>
  )
}

function Modal({ title, children, onClose, onSubmit, submitDisabled }: {
  title: string
  children: React.ReactNode
  onClose: () => void
  onSubmit: () => void
  submitDisabled?: boolean
}) {
  return (
    <DialogPrimitive.Root defaultOpen onOpenChange={open => {
      if (!open) onClose()
    }}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="dialog-overlay" onClick={onClose} />
        <DialogPrimitive.Content className="dialog-content" style={{ width: 440 }} aria-describedby={undefined}>
          <DialogPrimitive.Title className="dialog-title" style={{ fontSize: 17, marginBottom: 18 }}>{title}</DialogPrimitive.Title>
          {children}
          <div className="dialog-actions">
            <Button variant="secondary" size="md" onClick={onClose}>取消</Button>
            <Button variant="primary" size="md" onClick={onSubmit} disabled={submitDisabled}>保存</Button>
          </div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  )
}

function Labelled({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <label style={{ display: 'block', fontSize: 12, fontWeight: 500, color: 'var(--text-muted)', marginBottom: 6 }}>{label}</label>
      {children}
    </div>
  )
}

const selectStyle: React.CSSProperties = { padding: '7px 12px', border: '1px solid var(--border)', borderRadius: 6, fontSize: 13, fontFamily: 'inherit', background: 'var(--surface)', color: 'var(--text-secondary)', cursor: 'pointer' }
const modalInputStyle: React.CSSProperties = { width: '100%', padding: '9px 12px', border: '1px solid var(--border)', borderRadius: 7, fontSize: 13, fontFamily: 'inherit', background: 'var(--surface)', color: 'var(--text-primary)', boxSizing: 'border-box' }
const alertStyle: React.CSSProperties = { marginBottom: 14, padding: '9px 12px', border: '1px solid #FECACA', borderRadius: 6, background: 'var(--danger-bg)', color: 'var(--danger)', fontSize: 13 }
const emptyStyle: React.CSSProperties = { padding: '48px 20px', textAlign: 'center', color: 'var(--text-muted)', fontSize: 13 }
