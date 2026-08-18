import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as DialogPrimitive from '@radix-ui/react-dialog'
import { Plus, Search } from 'lucide-react'
import { adminKeys, createUser, listUsers, updateUser } from '../../../api/admin'
import { errorMessage } from '../../../api/request'
import type { AdminUser, UserRole } from '../../../api/types'
import { Button } from '../../../components/ui/Button'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { ADMIN_LIST_PAGE_SIZE } from './AdminPaging'
import { AdminEmptyState, AdminPageHeader, AdminPagination, AdminTableLoading, AdminTableSection } from './AdminUi'

interface EditModal {
  user: AdminUser
  role: UserRole
  // 空串表示「跟着角色的默认档走」。它与 0 是两回事。
  quota: string
  dept: string
}

const ROLE_LABEL: Record<UserRole, string> = {
  teacher: '教师',
  student: '学生',
  admin: '管理员',
  reviewer: '审核员',
}

const ROLE_CLASS: Record<UserRole, string> = {
  teacher: 'teacher',
  student: 'student',
  admin: 'admin',
  reviewer: 'reviewer',
}

const CREATABLE_ROLE: UserRole[] = ['teacher', 'student', 'reviewer', 'admin']
export function AdminUsers() {
  const queryClient = useQueryClient()
  const users = useQuery({ queryKey: adminKeys.users(), queryFn: listUsers })
  const [search, setSearch] = useState('')
  const [roleFilter, setRoleFilter] = useState<'all' | UserRole>('all')
  const [statusFilter, setStatusFilter] = useState<'all' | 'active' | 'disabled'>('all')
  const [page, setPage] = useState(1)
  const [editModal, setEditModal] = useState<EditModal | null>(null)
  const [creating, setCreating] = useState(false)
  const [disableTarget, setDisableTarget] = useState<AdminUser | null>(null)
  const [failure, setFailure] = useState('')

  const refresh = () => queryClient.invalidateQueries({ queryKey: adminKeys.users() })

  const change = useMutation({
    mutationFn: (input: { id: string; body: Parameters<typeof updateUser>[1] }) =>
      updateUser(input.id, input.body),
    onSuccess: () => { setPage(1); setFailure(''); void refresh() },
    onError: (reason) => setFailure(errorMessage(reason, '保存失败')),
  })

  const all = users.data ?? []
  // 待激活账号是管理员的首要任务，同表内置顶即可，无需再复制一张表。
  const ordered = [...all].sort((left, right) => Number(left.is_active) - Number(right.is_active))
  const pending = ordered.filter(one => !one.is_active)
  const normalizedSearch = search.trim().toLocaleLowerCase()
  const filtered = ordered.filter(one => {
    const matchSearch = !normalizedSearch
      || one.name.toLocaleLowerCase().includes(normalizedSearch)
      || one.email.toLocaleLowerCase().includes(normalizedSearch)
    const matchRole = roleFilter === 'all' || one.role === roleFilter
    const matchStatus = statusFilter === 'all' || (statusFilter === 'active' ? one.is_active : !one.is_active)
    return matchSearch && matchRole && matchStatus
  })
  const totalPages = Math.max(1, Math.ceil(filtered.length / ADMIN_LIST_PAGE_SIZE))
  const safePage = Math.min(page, totalPages)
  const visibleUsers = filtered.slice((safePage - 1) * ADMIN_LIST_PAGE_SIZE, safePage * ADMIN_LIST_PAGE_SIZE)

  const saveEdit = () => {
    if (!editModal) return
    const trimmed = editModal.quota.trim()
    change.mutate({
      id: editModal.user.id,
      body: {
        role: editModal.role,
        dept: editModal.dept,
        // 空串要传 null 才会清回默认档；不传表示这一项不动。
        quota_tokens_daily: trimmed === '' ? null : Number(trimmed),
      },
    })
    setEditModal(null)
  }

  const setStatus = (status: 'all' | 'active' | 'disabled') => {
    setStatusFilter(status)
    setPage(1)
  }

  return (
    <div className="admin-page">
      <AdminPageHeader
        eyebrow="ADMIN · ACCOUNTS"
        title="用户管理"
        description="集中管理账号、角色、院系与每日配额；待激活账号已自动排在最前。"
        pendingCount={pending.length}
        pendingLabel="个待处理"
        actions={<Button variant="primary" size="md" onClick={() => setCreating(true)}><Plus size={16} aria-hidden="true" />创建账号</Button>}
      />

      {users.isError && <div role="alert" className="admin-alert">{errorMessage(users.error)}</div>}
      {failure && <div role="alert" className="admin-alert">{failure}</div>}

      <AdminTableSection title="账号目录" action={<span className="admin-section-meta">{filtered.length} / {all.length} 个账号</span>}>
        <div className="admin-toolbar">
          <div className="admin-filter-tabs" role="group" aria-label="按账号状态筛选">
            {[
              { value: 'all' as const, label: '全部', count: all.length },
              { value: 'disabled' as const, label: '待激活', count: pending.length },
              { value: 'active' as const, label: '正常', count: all.length - pending.length },
            ].map(option => (
              <button
                key={option.value}
                type="button"
                className={`admin-filter-tab${statusFilter === option.value ? ' active' : ''}`}
                aria-pressed={statusFilter === option.value}
                onClick={() => setStatus(option.value)}
              >
                {option.label} <span>{option.count}</span>
              </button>
            ))}
          </div>

          <div className="admin-toolbar-fields">
            <label className="admin-search-field">
              <span className="sr-only">搜索账号</span>
              <Search size={16} aria-hidden="true" />
              <input
                type="search"
                aria-label="搜索账号"
                value={search}
                onChange={event => { setSearch(event.target.value); setPage(1) }}
                placeholder="搜索用户名或邮箱"
              />
            </label>
            <select
              className="admin-field admin-select"
              aria-label="按角色筛选"
              value={roleFilter}
              onChange={event => { setRoleFilter(event.target.value as 'all' | UserRole); setPage(1) }}
            >
              <option value="all">全部角色</option>
              {CREATABLE_ROLE.map(role => <option key={role} value={role}>{ROLE_LABEL[role]}</option>)}
            </select>
          </div>
        </div>

        {users.isPending ? (
          <AdminTableLoading label="正在加载账号列表…" />
        ) : filtered.length === 0 ? (
          <AdminEmptyState title="没有匹配的账号" description="请调整关键词、角色或状态筛选。" />
        ) : (
          <>
            <div className="admin-table-scroll">
              <table className="admin-table admin-table-users admin-table--actions">
                <thead><tr>{['用户名', '邮箱', '院系', '角色', '日配额', '状态', '操作'].map(label => <th key={label}>{label}</th>)}</tr></thead>
                <tbody>
                  {visibleUsers.map(user => (
                    <tr key={user.id}>
                      <td className="admin-table-name"><span className="admin-truncate" title={user.name}>{user.name}</span></td>
                      <td><span className="admin-truncate admin-email" title={user.email}>{user.email}</span></td>
                      <td>{user.dept || '—'}</td>
                      <td><span className={`admin-role-badge ${ROLE_CLASS[user.role]}`}>{ROLE_LABEL[user.role]}</span></td>
                      <td className="admin-table-mono">{user.quota_tokens_daily === null ? '默认' : user.quota_tokens_daily.toLocaleString()}</td>
                      <td><span className={`admin-status ${user.is_active ? 'success' : 'muted'}`}>{user.is_active ? '正常' : '待激活'}</span></td>
                      <td>
                        <div className="admin-table-actions">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => setEditModal({
                              user,
                              role: user.role,
                              quota: user.quota_tokens_daily === null ? '' : String(user.quota_tokens_daily),
                              dept: user.dept,
                            })}
                          >
                            编辑
                          </Button>
                          {user.is_active ? (
                            <Button variant="secondary" size="sm" className="admin-danger-action" onClick={() => setDisableTarget(user)}>停用</Button>
                          ) : (
                            <Button
                              variant="secondary"
                              size="sm"
                              className="admin-success-action"
                              disabled={change.isPending}
                              onClick={() => change.mutate({ id: user.id, body: { is_active: true } })}
                            >
                              激活
                            </Button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <AdminPagination page={safePage} pageSize={ADMIN_LIST_PAGE_SIZE} totalItems={filtered.length} itemName="账号" onPageChange={setPage} />
          </>
        )}
      </AdminTableSection>

      {editModal && (
        <Modal title={`编辑账号：${editModal.user.name}`} onClose={() => setEditModal(null)} onSubmit={saveEdit}>
          <Labelled id="edit-user-role" label="角色">
            <select id="edit-user-role" value={editModal.role} onChange={event => setEditModal({ ...editModal, role: event.target.value as UserRole })} className="admin-form-control">
              {CREATABLE_ROLE.map(role => <option key={role} value={role}>{ROLE_LABEL[role]}</option>)}
            </select>
          </Labelled>
          <Labelled id="edit-user-dept" label="院系">
            <input id="edit-user-dept" value={editModal.dept} onChange={event => setEditModal({ ...editModal, dept: event.target.value })} className="admin-form-control" />
          </Labelled>
          <Labelled id="edit-user-quota" label="每日 Token 配额（留空＝跟随角色默认档）">
            <input id="edit-user-quota" type="number" min={0} value={editModal.quota} placeholder="默认" onChange={event => setEditModal({ ...editModal, quota: event.target.value })} className="admin-form-control" />
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

      <ConfirmDialog
        open={disableTarget !== null}
        title={`停用账号「${disableTarget?.name ?? ''}」？`}
        message="停用后该账号将无法登录或发起分析，之后仍可由管理员重新启用。"
        confirmLabel="确认停用"
        danger
        onCancel={() => setDisableTarget(null)}
        onConfirm={() => {
          if (disableTarget) change.mutate({ id: disableTarget.id, body: { is_active: false } })
          setDisableTarget(null)
        }}
      />
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
    <Modal title="创建账号" submitLabel="创建账号" onClose={onClose} onSubmit={() => ready && create.mutate()} submitDisabled={!ready || create.isPending}>
      <Labelled id="create-user-name" label="用户名"><input id="create-user-name" autoComplete="off" value={name} onChange={event => setName(event.target.value)} className="admin-form-control" /></Labelled>
      <Labelled id="create-user-email" label="邮箱（可作为登录账号）"><input id="create-user-email" type="email" autoComplete="off" value={email} onChange={event => setEmail(event.target.value)} className="admin-form-control" /></Labelled>
      <Labelled id="create-user-password" label="初始口令（至少 8 位）"><input id="create-user-password" type="password" autoComplete="new-password" value={password} onChange={event => setPassword(event.target.value)} className="admin-form-control" /></Labelled>
      <Labelled id="create-user-dept" label="院系"><input id="create-user-dept" value={dept} onChange={event => setDept(event.target.value)} className="admin-form-control" /></Labelled>
      <Labelled id="create-user-role" label="角色">
        <select id="create-user-role" value={role} onChange={event => setRole(event.target.value as UserRole)} className="admin-form-control">
          {CREATABLE_ROLE.map(one => <option key={one} value={one}>{ROLE_LABEL[one]}</option>)}
        </select>
      </Labelled>
    </Modal>
  )
}

function Modal({ title, children, onClose, onSubmit, submitDisabled, submitLabel = '保存' }: {
  title: string
  children: React.ReactNode
  onClose: () => void
  onSubmit: () => void
  submitDisabled?: boolean
  submitLabel?: string
}) {
  return (
    <DialogPrimitive.Root defaultOpen onOpenChange={open => {
      if (!open) onClose()
    }}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="dialog-overlay" onClick={onClose} />
        <DialogPrimitive.Content className="dialog-content admin-account-dialog" aria-describedby={undefined}>
          <DialogPrimitive.Title className="dialog-title admin-account-dialog-title">{title}</DialogPrimitive.Title>
          {children}
          <div className="dialog-actions">
            <Button variant="secondary" size="md" onClick={onClose}>取消</Button>
            <Button variant="primary" size="md" onClick={onSubmit} disabled={submitDisabled}>{submitLabel}</Button>
          </div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  )
}

function Labelled({ id, label, children }: { id: string; label: string; children: React.ReactNode }) {
  return (
    <div className="admin-form-field">
      <label htmlFor={id}>{label}</label>
      {children}
    </div>
  )
}
