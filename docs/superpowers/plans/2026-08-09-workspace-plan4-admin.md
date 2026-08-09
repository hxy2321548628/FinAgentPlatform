# 工作台 Plan 4：管理后台 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现管理后台的五个子页面（用户管理 + 注册审批 + 智能体审核 + 用量看板 + 系统状态），以及管理后台的落地路由。

**Architecture:** 管理后台所有页面放在 `workspace/pages/admin/` 目录下，通过 `/workspace/admin/*` 路由挂载。`AdminLayout` 作为管理后台的共同布局（含子菜单导航），各子页面作为 `<Outlet />` 渲染。WorkspaceRouter 中原来的 `admin/*` 占位直接替换为真实路由树。

**Tech Stack:** React 18 + TypeScript · 内联 style + CSS 变量 · useState 管理 UI 交互状态

---

## 文件结构

```
web/src/workspace/pages/admin/
├── AdminLayout.tsx        ← 新建：管理后台布局 + 子菜单
├── AdminUsers.tsx         ← 新建：用户管理 + 注册审批（合并到一页）
├── AdminAgents.tsx        ← 新建：智能体审核
├── AdminUsage.tsx         ← 新建：用量看板
└── AdminSystem.tsx        ← 新建：系统状态
web/src/workspace/
└── WorkspaceRouter.tsx    ← 修改：接入 admin/* 路由树
```

---

### Task 1：AdminLayout + AdminUsers（用户管理 + 注册审批）

**Files:**
- Create: `web/src/workspace/pages/admin/AdminLayout.tsx`
- Create: `web/src/workspace/pages/admin/AdminUsers.tsx`

- [ ] **Step 1: 创建 AdminLayout.tsx**

```tsx
import { NavLink, Outlet, useNavigate } from 'react-router-dom'

const ADMIN_NAV = [
  { to: '/workspace/admin/users', label: '用户管理', icon: '👥' },
  { to: '/workspace/admin/agents', label: '智能体审核', icon: '🔍' },
  { to: '/workspace/admin/usage', label: '用量看板', icon: '📊' },
  { to: '/workspace/admin/system', label: '系统状态', icon: '🖥' },
]

export function AdminLayout() {
  const navigate = useNavigate()
  return (
    <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
      {/* 管理后台子菜单 */}
      <div style={{ width: 180, flexShrink: 0, background: 'var(--surface)', borderRight: '1px solid var(--border)', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <div style={{ padding: '16px 16px 10px' }}>
          <div style={{ fontSize: 10, fontFamily: "'JetBrains Mono', monospace", textTransform: 'uppercase' as const, letterSpacing: '0.2em', color: 'var(--text-muted)', marginBottom: 4 }}>// ADMIN</div>
          <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)' }}>管理后台</div>
        </div>
        <div style={{ height: 1, background: 'var(--border-light)' }} />
        <nav style={{ flex: 1, padding: '6px 8px' }}>
          {ADMIN_NAV.map(item => (
            <NavLink
              key={item.to}
              to={item.to}
              style={({ isActive }) => ({
                display: 'flex', alignItems: 'center', gap: 8,
                padding: '8px 10px', borderRadius: 6, marginBottom: 2,
                fontSize: 13, textDecoration: 'none',
                background: isActive ? 'var(--action-light)' : 'transparent',
                color: isActive ? 'var(--action)' : 'var(--text-secondary)',
                fontWeight: isActive ? 600 : 400,
                transition: 'background 0.15s, color 0.15s',
              })}
            >
              <span style={{ fontSize: 14 }}>{item.icon}</span>
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div style={{ padding: '10px 8px', borderTop: '1px solid var(--border-light)' }}>
          <button
            onClick={() => navigate('/workspace')}
            style={{ width: '100%', padding: '7px 10px', display: 'flex', alignItems: 'center', gap: 8, background: 'none', border: 'none', cursor: 'pointer', fontSize: 12, color: 'var(--text-muted)', fontFamily: 'inherit', borderRadius: 6 }}
          >
            ← 返回工作台
          </button>
        </div>
      </div>
      {/* 子页面内容 */}
      <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
        <Outlet />
      </div>
    </div>
  )
}
```

- [ ] **Step 2: 创建 AdminUsers.tsx（用户管理 + 注册审批合并）**

```tsx
import { useState } from 'react'

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

interface EditModal {
  user: User
  quota: number
  role: Role
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

  const handleToggleStatus = (id: string) => {
    setUsers(prev => prev.map(u => u.id === id ? { ...u, status: u.status === 'active' ? 'disabled' : 'active' } : u))
  }

  const handleSaveEdit = () => {
    if (!editModal) return
    setUsers(prev => prev.map(u => u.id === editModal.user.id ? { ...u, role: editModal.role, quota: editModal.quota } : u))
    setEditModal(null)
  }

  const handleApprove = (id: string, pendingUser: PendingUser) => {
    const newUser: User = {
      id: `new-${id}`, name: pendingUser.name, email: pendingUser.email,
      role: pendingUser.identity === '教师' ? 'teacher' : 'student',
      quota: pendingUser.identity === '教师' ? 120 : 40,
      status: 'active', createdAt: new Date().toISOString().split('T')[0],
    }
    setUsers(prev => [newUser, ...prev])
    setPending(prev => prev.filter(p => p.id !== id))
  }

  const handleReject = (id: string) => {
    setPending(prev => prev.filter(p => p.id !== id))
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '28px 32px', background: 'var(--bg)' }}>
      {/* 注册审批（高优先级，置顶） */}
      {pending.length > 0 && (
        <div style={{ background: 'var(--surface)', border: '1px solid var(--action-border)', borderRadius: 10, marginBottom: 20, overflow: 'hidden' }}>
          <div style={{ padding: '14px 20px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: 'var(--action-light)' }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--action)', fontFamily: "'JetBrains Mono', monospace", fontSize: 11, textTransform: 'uppercase' as const, letterSpacing: '0.2em' }}>
              // PENDING APPROVALS
            </div>
            <span style={{ padding: '2px 10px', background: 'var(--action)', color: '#fff', borderRadius: 20, fontSize: 12, fontWeight: 700 }}>{pending.length} 个待处理</span>
          </div>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr>
                {['申请人', '邮箱', '院系', '身份', '申请时间', '操作'].map(h => (
                  <th key={h} style={{ padding: '10px 16px', textAlign: 'left' as const, fontSize: 11, color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase' as const, letterSpacing: '0.08em', borderBottom: '1px solid var(--border-light)', background: 'var(--bg)' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {pending.map((p, i) => (
                <tr key={p.id} style={{ borderBottom: i < pending.length - 1 ? '1px solid var(--border-light)' : 'none' }}>
                  <td style={{ padding: '12px 16px', fontWeight: 500, color: 'var(--text-primary)' }}>{p.name}</td>
                  <td style={{ padding: '12px 16px', color: 'var(--text-secondary)', fontSize: 12 }}>{p.email}</td>
                  <td style={{ padding: '12px 16px', color: 'var(--text-secondary)' }}>{p.dept}</td>
                  <td style={{ padding: '12px 16px' }}>
                    <span style={{ padding: '2px 8px', borderRadius: 4, fontSize: 11, fontWeight: 600, background: p.identity === '教师' ? '#EFF6FF' : '#F5F3FF', color: p.identity === '教师' ? '#2563EB' : '#7C3AED' }}>{p.identity}</span>
                  </td>
                  <td style={{ padding: '12px 16px', color: 'var(--text-muted)', fontSize: 12 }}>{p.appliedAt}</td>
                  <td style={{ padding: '12px 16px' }}>
                    <div style={{ display: 'flex', gap: 6 }}>
                      <button onClick={() => handleApprove(p.id, p)} style={{ padding: '5px 12px', background: 'var(--status-done)', color: '#fff', border: 'none', borderRadius: 5, fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>激活</button>
                      <button onClick={() => handleReject(p.id)} style={{ padding: '5px 12px', background: 'transparent', color: '#DC2626', border: '1px solid #FECACA', borderRadius: 5, fontSize: 12, cursor: 'pointer', fontFamily: 'inherit' }}>拒绝</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* 用户管理 */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <div style={{ fontSize: 10, fontFamily: "'JetBrains Mono', monospace", textTransform: 'uppercase' as const, letterSpacing: '0.3em', color: 'var(--text-muted)' }}>// USER MANAGEMENT</div>
        <button style={{ padding: '7px 16px', background: 'var(--action)', color: '#fff', border: 'none', borderRadius: 6, fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>+ 创建账号</button>
      </div>

      {/* 筛选栏 */}
      <div style={{ display: 'flex', gap: 10, marginBottom: 14, flexWrap: 'wrap' as const }}>
        <input value={search} onChange={e => setSearch(e.target.value)} placeholder="搜索姓名或邮箱" style={{ padding: '7px 12px', border: '1px solid var(--border)', borderRadius: 6, fontSize: 13, fontFamily: 'inherit', outline: 'none', background: 'var(--surface)', color: 'var(--text-primary)', width: 200 }} />
        <select value={roleFilter} onChange={e => setRoleFilter(e.target.value as 'all' | Role)} style={{ padding: '7px 12px', border: '1px solid var(--border)', borderRadius: 6, fontSize: 13, fontFamily: 'inherit', background: 'var(--surface)', color: 'var(--text-secondary)', cursor: 'pointer' }}>
          <option value="all">全部角色</option>
          <option value="teacher">教师</option>
          <option value="student">学生</option>
          <option value="admin">管理员</option>
        </select>
        <select value={statusFilter} onChange={e => setStatusFilter(e.target.value as 'all' | UserStatus)} style={{ padding: '7px 12px', border: '1px solid var(--border)', borderRadius: 6, fontSize: 13, fontFamily: 'inherit', background: 'var(--surface)', color: 'var(--text-secondary)', cursor: 'pointer' }}>
          <option value="all">全部状态</option>
          <option value="active">正常</option>
          <option value="disabled">已禁用</option>
        </select>
      </div>

      {/* 用户列表 */}
      <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr>
              {['姓名', '邮箱', '角色', '配额（月）', '状态', '注册时间', '操作'].map(h => (
                <th key={h} style={{ padding: '10px 16px', textAlign: 'left' as const, fontSize: 11, color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase' as const, letterSpacing: '0.08em', borderBottom: '1px solid var(--border)', background: 'var(--bg)' }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.map((user, i) => {
              const rs = ROLE_STYLE[user.role]
              return (
                <tr key={user.id} style={{ borderBottom: i < filtered.length - 1 ? '1px solid var(--border-light)' : 'none', opacity: user.status === 'disabled' ? 0.6 : 1 }}>
                  <td style={{ padding: '12px 16px', fontWeight: 500, color: 'var(--text-primary)' }}>{user.name}</td>
                  <td style={{ padding: '12px 16px', color: 'var(--text-secondary)', fontSize: 12 }}>{user.email}</td>
                  <td style={{ padding: '12px 16px' }}>
                    <span style={{ padding: '2px 8px', borderRadius: 4, fontSize: 11, fontWeight: 600, background: rs.bg, color: rs.color }}>{ROLE_LABEL[user.role]}</span>
                  </td>
                  <td style={{ padding: '12px 16px', fontSize: 12, fontFamily: "'JetBrains Mono', monospace", color: 'var(--text-secondary)' }}>{user.quota}K tokens</td>
                  <td style={{ padding: '12px 16px' }}>
                    <span style={{ fontSize: 12, fontWeight: 600, color: user.status === 'active' ? 'var(--status-done)' : 'var(--text-muted)' }}>
                      {user.status === 'active' ? '● 正常' : '○ 已禁用'}
                    </span>
                  </td>
                  <td style={{ padding: '12px 16px', fontSize: 12, color: 'var(--text-muted)' }}>{user.createdAt}</td>
                  <td style={{ padding: '12px 16px' }}>
                    <div style={{ display: 'flex', gap: 6 }}>
                      <button onClick={() => setEditModal({ user, quota: user.quota, role: user.role })} style={{ padding: '4px 10px', background: 'transparent', color: 'var(--action)', border: '1px solid var(--action-border)', borderRadius: 5, fontSize: 11, cursor: 'pointer', fontFamily: 'inherit' }}>编辑</button>
                      {user.role !== 'admin' && (
                        <button onClick={() => handleToggleStatus(user.id)} style={{ padding: '4px 10px', background: 'transparent', color: user.status === 'active' ? '#DC2626' : 'var(--status-done)', border: '1px solid ' + (user.status === 'active' ? '#FECACA' : '#A7F3D0'), borderRadius: 5, fontSize: 11, cursor: 'pointer', fontFamily: 'inherit' }}>
                          {user.status === 'active' ? '禁用' : '启用'}
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {/* 编辑弹窗 */}
      {editModal && (
        <>
          <div onClick={() => setEditModal(null)} style={{ position: 'fixed', inset: 0, background: 'rgba(13,24,41,0.4)', backdropFilter: 'blur(4px)', zIndex: 200 }} />
          <div style={{ position: 'fixed', top: '50%', left: '50%', transform: 'translate(-50%,-50%)', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12, padding: 32, width: 400, zIndex: 201, boxShadow: '0 20px 60px rgba(11,46,92,0.2)' }}>
            <div style={{ fontSize: 17, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 24 }}>编辑用户：{editModal.user.name}</div>
            <div style={{ marginBottom: 16 }}>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 500, color: 'var(--text-muted)', marginBottom: 6, textTransform: 'uppercase' as const, letterSpacing: '0.1em' }}>角色</label>
              <select value={editModal.role} onChange={e => setEditModal({ ...editModal, role: e.target.value as Role })} style={{ width: '100%', padding: '9px 12px', border: '1px solid var(--border)', borderRadius: 7, fontSize: 13, fontFamily: 'inherit', background: 'var(--surface)', color: 'var(--text-primary)', outline: 'none' }}>
                <option value="teacher">教师</option>
                <option value="student">学生</option>
                <option value="admin">管理员</option>
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
```

- [ ] **Step 3: TypeScript 检查**

```bash
cd "/d/Desktop/evolution/0 program/8-FinAgentPlantform/frontend/FinAgentPlatform/web" && pnpm tsc --noEmit 2>&1 | head -15
```

Expected: 无相关报错。

- [ ] **Step 4: Commit**

```bash
cd "/d/Desktop/evolution/0 program/8-FinAgentPlantform/frontend/FinAgentPlatform" && git add web/src/workspace/pages/admin/AdminLayout.tsx web/src/workspace/pages/admin/AdminUsers.tsx && git -c user.email="dev@finagent.local" -c user.name="FinAgent Dev" commit -m "feat(admin): add admin layout and user management with approval queue"
```

---

### Task 2：AdminAgents + AdminUsage + AdminSystem + 路由接入

**Files:**
- Create: `web/src/workspace/pages/admin/AdminAgents.tsx`
- Create: `web/src/workspace/pages/admin/AdminUsage.tsx`
- Create: `web/src/workspace/pages/admin/AdminSystem.tsx`
- Modify: `web/src/workspace/WorkspaceRouter.tsx`

- [ ] **Step 1: 创建 AdminAgents.tsx（智能体审核）**

```tsx
import { useState } from 'react'

interface PendingAgent {
  id: string; name: string; author: string; subject: string
  desc: string; dataNeeded: string; prompt: string; submittedAt: string
}

const MOCK_PENDING_AGENTS: PendingAgent[] = [
  { id: '1', name: '企业财务异常检测 v2', author: '张老师', subject: '金融学', desc: '对报表关键科目进行稽核式比率检查，识别异常项并输出清单。升级版增加了行业对比维度。', dataNeeded: '财报 Excel / CSV', prompt: '你是一位专业的财务分析师，擅长识别财务报表中的异常信号。\n\n请按以下步骤分析：\n1. 读取财务报表数据\n2. 计算流动比率、速动比率、资产负债率等关键指标\n3. 与行业平均水平对比，识别偏离超过 1.5 个标准差的指标\n4. 输出异常项清单，每项注明具体数值和判断依据\n5. 给出综合风险评级（高/中/低）', submittedAt: '2026-08-09 14:22' },
  { id: '2', name: '量化因子筛选器', author: '李教授', subject: '金融学', desc: '基于历史收益率数据构建多因子模型，筛选具有显著 alpha 的因子组合。', dataNeeded: '股票日 K 数据 CSV', prompt: '你是一位量化研究员。\n\n请基于上传的股票数据：\n1. 计算常见因子值（动量、市值、市盈率等）\n2. 使用 Fama-French 框架进行因子回归\n3. 检验因子的 alpha 显著性（t 检验，p < 0.05）\n4. 输出显著因子列表及其因子暴露', submittedAt: '2026-08-08 09:15' },
]

export function AdminAgents() {
  const [agents, setAgents] = useState(MOCK_PENDING_AGENTS)
  const [detailId, setDetailId] = useState<string | null>(null)
  const [rejectReason, setRejectReason] = useState('')

  const detailAgent = agents.find(a => a.id === detailId)

  const handleApprove = (id: string) => {
    setAgents(prev => prev.filter(a => a.id !== id))
    if (detailId === id) setDetailId(null)
  }

  const handleReject = (id: string) => {
    setAgents(prev => prev.filter(a => a.id !== id))
    if (detailId === id) { setDetailId(null); setRejectReason('') }
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '28px 32px', background: 'var(--bg)' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
        <div>
          <div style={{ fontSize: 10, fontFamily: "'JetBrains Mono', monospace", textTransform: 'uppercase' as const, letterSpacing: '0.3em', color: 'var(--text-muted)', marginBottom: 4 }}>// AGENT REVIEW</div>
          <h1 style={{ fontSize: 22, fontWeight: 700, color: 'var(--text-primary)' }}>智能体审核</h1>
        </div>
        <span style={{ padding: '4px 14px', background: agents.length > 0 ? 'var(--action-light)' : 'var(--bg)', color: agents.length > 0 ? 'var(--action)' : 'var(--text-muted)', border: '1px solid ' + (agents.length > 0 ? 'var(--action-border)' : 'var(--border)'), borderRadius: 20, fontSize: 13, fontWeight: 600 }}>
          {agents.length} 个待审核
        </span>
      </div>

      {agents.length === 0 ? (
        <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, padding: '60px 20px', textAlign: 'center' as const }}>
          <div style={{ fontSize: 32, marginBottom: 12 }}>✓</div>
          <div style={{ fontSize: 14, fontWeight: 500, color: 'var(--text-primary)' }}>暂无待审核的智能体</div>
        </div>
      ) : (
        <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, overflow: 'hidden' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr>
                {['智能体名称', '创建者', '学科', '提交时间', '操作'].map(h => (
                  <th key={h} style={{ padding: '10px 16px', textAlign: 'left' as const, fontSize: 11, color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase' as const, letterSpacing: '0.08em', borderBottom: '1px solid var(--border)', background: 'var(--bg)' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {agents.map((agent, i) => (
                <tr key={agent.id} style={{ borderBottom: i < agents.length - 1 ? '1px solid var(--border-light)' : 'none' }}>
                  <td style={{ padding: '12px 16px', fontWeight: 500, color: 'var(--text-primary)' }}>{agent.name}</td>
                  <td style={{ padding: '12px 16px', color: 'var(--text-secondary)' }}>{agent.author}</td>
                  <td style={{ padding: '12px 16px', color: 'var(--text-muted)', fontSize: 12 }}>{agent.subject}</td>
                  <td style={{ padding: '12px 16px', color: 'var(--text-muted)', fontSize: 12, fontFamily: "'JetBrains Mono', monospace" }}>{agent.submittedAt}</td>
                  <td style={{ padding: '12px 16px' }}>
                    <div style={{ display: 'flex', gap: 6 }}>
                      <button onClick={() => setDetailId(agent.id)} style={{ padding: '5px 12px', background: 'transparent', color: 'var(--action)', border: '1px solid var(--action-border)', borderRadius: 5, fontSize: 12, cursor: 'pointer', fontFamily: 'inherit' }}>查看详情</button>
                      <button onClick={() => handleApprove(agent.id)} style={{ padding: '5px 12px', background: 'var(--status-done)', color: '#fff', border: 'none', borderRadius: 5, fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>通过</button>
                      <button onClick={() => handleReject(agent.id)} style={{ padding: '5px 12px', background: 'transparent', color: '#DC2626', border: '1px solid #FECACA', borderRadius: 5, fontSize: 12, cursor: 'pointer', fontFamily: 'inherit' }}>拒绝</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* 详情侧抽屉 */}
      {detailAgent && (
        <>
          <div onClick={() => setDetailId(null)} style={{ position: 'fixed', inset: 0, background: 'rgba(13,24,41,0.3)', zIndex: 200 }} />
          <div style={{ position: 'fixed', top: 0, right: 0, bottom: 0, width: 480, background: 'var(--surface)', borderLeft: '1px solid var(--border)', zIndex: 201, display: 'flex', flexDirection: 'column', boxShadow: '-8px 0 24px rgba(11,46,92,0.12)' }}>
            <div style={{ padding: '20px 24px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)' }}>{detailAgent.name}</div>
              <button onClick={() => setDetailId(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', fontSize: 20, lineHeight: 1 }}>×</button>
            </div>
            <div style={{ flex: 1, overflowY: 'auto', padding: '20px 24px' }}>
              <InfoRow label="创建者" value={detailAgent.author} />
              <InfoRow label="学科" value={detailAgent.subject} />
              <InfoRow label="所需数据" value={detailAgent.dataNeeded} />
              <div style={{ marginBottom: 16 }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' as const, letterSpacing: '0.1em', marginBottom: 6 }}>功能描述</div>
                <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.7 }}>{detailAgent.desc}</div>
              </div>
              <div style={{ marginBottom: 20 }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' as const, letterSpacing: '0.1em', marginBottom: 8 }}>系统提示词（审核核心）</div>
                <div style={{ background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 6, padding: '12px 14px', fontSize: 12, fontFamily: "'JetBrains Mono', monospace", color: 'var(--text-secondary)', lineHeight: 1.8, whiteSpace: 'pre-wrap' as const }}>
                  {detailAgent.prompt}
                </div>
              </div>
              <div>
                <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' as const, letterSpacing: '0.1em', marginBottom: 8 }}>拒绝理由（可选）</div>
                <textarea value={rejectReason} onChange={e => setRejectReason(e.target.value)} placeholder="填写拒绝理由，将通知给创建者..." style={{ width: '100%', minHeight: 80, padding: '8px 12px', border: '1px solid var(--border)', borderRadius: 6, fontSize: 12, fontFamily: 'inherit', resize: 'vertical' as const, background: 'var(--surface)', outline: 'none', boxSizing: 'border-box' as const, color: 'var(--text-primary)' }} />
              </div>
            </div>
            <div style={{ padding: '16px 24px', borderTop: '1px solid var(--border)', display: 'flex', gap: 10 }}>
              <button onClick={() => handleApprove(detailAgent.id)} style={{ flex: 1, padding: '9px', background: 'var(--status-done)', color: '#fff', border: 'none', borderRadius: 7, fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>✓ 通过</button>
              <button onClick={() => handleReject(detailAgent.id)} style={{ flex: 1, padding: '9px', background: '#DC2626', color: '#fff', border: 'none', borderRadius: 7, fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>✗ 拒绝</button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: 'flex', gap: 16, marginBottom: 12, alignItems: 'flex-start' }}>
      <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' as const, letterSpacing: '0.1em', width: 70, flexShrink: 0, paddingTop: 1 }}>{label}</div>
      <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{value}</div>
    </div>
  )
}
```

- [ ] **Step 2: 创建 AdminUsage.tsx（用量看板）**

```tsx
const MOCK_STATS = { totalRuns: 312, totalTokens: 4280000, totalCost: 42.8, activeUsers: 18 }

const MOCK_USER_USAGE = [
  { name: '张老师', tokens: 45230, runs: 12, cost: 3.2 },
  { name: '李教授', tokens: 38910, runs: 9, cost: 2.8 },
  { name: '赵同学', tokens: 21430, runs: 7, cost: 1.5 },
  { name: '陈研究生', tokens: 18760, runs: 5, cost: 1.3 },
  { name: '孙老师', tokens: 15200, runs: 4, cost: 1.1 },
]

export function AdminUsage() {
  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '28px 32px', background: 'var(--bg)' }}>
      <div style={{ marginBottom: 24 }}>
        <div style={{ fontSize: 10, fontFamily: "'JetBrains Mono', monospace", textTransform: 'uppercase' as const, letterSpacing: '0.3em', color: 'var(--text-muted)', marginBottom: 4 }}>// USAGE DASHBOARD</div>
        <h1 style={{ fontSize: 22, fontWeight: 700, color: 'var(--text-primary)' }}>用量看板</h1>
        <p style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 4 }}>统计周期：2026-08-01 ~ 2026-08-09</p>
      </div>

      {/* 统计卡片 */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14, marginBottom: 28 }}>
        {[
          { label: 'TOTAL RUNS', value: MOCK_STATS.totalRuns.toLocaleString(), unit: '次分析' },
          { label: 'TOKENS USED', value: (MOCK_STATS.totalTokens / 1000000).toFixed(1) + 'M', unit: 'tokens 消耗' },
          { label: 'EST. COST', value: '¥' + MOCK_STATS.totalCost.toFixed(1), unit: '估算费用', accent: true },
          { label: 'ACTIVE USERS', value: MOCK_STATS.activeUsers.toString(), unit: '活跃用户' },
        ].map(s => (
          <div key={s.label} style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, padding: '18px 20px' }}>
            <div style={{ fontSize: 10, fontFamily: "'JetBrains Mono', monospace", textTransform: 'uppercase' as const, letterSpacing: '0.12em', color: 'var(--text-muted)', marginBottom: 8 }}>{s.label}</div>
            <div style={{ fontSize: 26, fontWeight: 800, color: s.accent ? 'var(--action)' : 'var(--text-primary)', fontFamily: "'JetBrains Mono', monospace", lineHeight: 1, marginBottom: 4 }}>{s.value}</div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{s.unit}</div>
          </div>
        ))}
      </div>

      {/* 用量排行 */}
      <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, overflow: 'hidden' }}>
        <div style={{ padding: '14px 20px', borderBottom: '1px solid var(--border)', fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>用量排行（本月）</div>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr>
              {['排名', '用户', '本月 Tokens', '本月 Run 数', '估算费用'].map(h => (
                <th key={h} style={{ padding: '10px 20px', textAlign: 'left' as const, fontSize: 11, color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase' as const, letterSpacing: '0.08em', borderBottom: '1px solid var(--border-light)', background: 'var(--bg)' }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {MOCK_USER_USAGE.map((u, i) => (
              <tr key={u.name} style={{ borderBottom: i < MOCK_USER_USAGE.length - 1 ? '1px solid var(--border-light)' : 'none' }}>
                <td style={{ padding: '12px 20px', fontSize: 12, fontFamily: "'JetBrains Mono', monospace", color: i < 3 ? 'var(--action)' : 'var(--text-muted)', fontWeight: i < 3 ? 700 : 400 }}>#{i + 1}</td>
                <td style={{ padding: '12px 20px', fontWeight: 500, color: 'var(--text-primary)' }}>{u.name}</td>
                <td style={{ padding: '12px 20px', fontFamily: "'JetBrains Mono', monospace", fontSize: 12, color: 'var(--text-secondary)' }}>{u.tokens.toLocaleString()}</td>
                <td style={{ padding: '12px 20px', color: 'var(--text-secondary)' }}>{u.runs}</td>
                <td style={{ padding: '12px 20px', fontFamily: "'JetBrains Mono', monospace", fontSize: 12, color: 'var(--action)', fontWeight: 500 }}>¥{u.cost}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
```

- [ ] **Step 3: 创建 AdminSystem.tsx（系统状态）**

```tsx
const SYSTEM_ITEMS = [
  { label: 'Worker', status: 'online' as const, detail: '2 个实例运行中' },
  { label: 'Postgres', status: 'online' as const, detail: '主库在线，备份正常' },
  { label: 'Redis', status: 'online' as const, detail: '内存使用 23%' },
  { label: 'MinIO', status: 'online' as const, detail: '对象存储在线' },
]

export function AdminSystem() {
  const sandboxUsed = 6
  const sandboxTotal = 20
  const sandboxPct = Math.round(sandboxUsed / sandboxTotal * 100)

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '28px 32px', background: 'var(--bg)' }}>
      <div style={{ marginBottom: 24 }}>
        <div style={{ fontSize: 10, fontFamily: "'JetBrains Mono', monospace", textTransform: 'uppercase' as const, letterSpacing: '0.3em', color: 'var(--text-muted)', marginBottom: 4 }}>// SYSTEM STATUS</div>
        <h1 style={{ fontSize: 22, fontWeight: 700, color: 'var(--text-primary)' }}>系统状态</h1>
      </div>

      {/* 沙箱池 */}
      <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, padding: 24, marginBottom: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
          <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>沙箱池</div>
          <span style={{ fontSize: 13, fontFamily: "'JetBrains Mono', monospace", color: 'var(--text-secondary)' }}>{sandboxUsed} / {sandboxTotal} 占用</span>
        </div>
        <div style={{ height: 10, background: 'var(--border-light)', borderRadius: 5, overflow: 'hidden', marginBottom: 8 }}>
          <div style={{ height: '100%', width: `${sandboxPct}%`, background: sandboxPct > 80 ? 'var(--status-warn)' : 'var(--action)', borderRadius: 5, transition: 'width 0.4s' }} />
        </div>
        <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
          剩余 {sandboxTotal - sandboxUsed} 个沙箱可用 · 单沙箱内存上限 2GB · gVisor 隔离
        </div>
      </div>

      {/* 服务状态 */}
      <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, overflow: 'hidden' }}>
        <div style={{ padding: '14px 20px', borderBottom: '1px solid var(--border)', fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>服务状态</div>
        <div style={{ display: 'flex', flexDirection: 'column' as const }}>
          {SYSTEM_ITEMS.map((item, i) => (
            <div key={item.label} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '14px 20px', borderBottom: i < SYSTEM_ITEMS.length - 1 ? '1px solid var(--border-light)' : 'none' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <span style={{ width: 8, height: 8, borderRadius: '50%', background: item.status === 'online' ? 'var(--status-done)' : '#DC2626', display: 'inline-block', boxShadow: item.status === 'online' ? '0 0 0 2px rgba(16,185,129,0.2)' : 'none' }} />
                <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>{item.label}</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{item.detail}</span>
                <span style={{ fontSize: 12, fontWeight: 600, color: item.status === 'online' ? 'var(--status-done)' : '#DC2626' }}>
                  {item.status === 'online' ? '◉ 在线' : '○ 离线'}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 4: 修改 WorkspaceRouter.tsx 接入 admin 路由树**

先 Read `WorkspaceRouter.tsx`，然后：

1. 在文件顶部 import 区追加：
```tsx
import { AdminLayout } from './pages/admin/AdminLayout'
import { AdminUsers } from './pages/admin/AdminUsers'
import { AdminAgents } from './pages/admin/AdminAgents'
import { AdminUsage } from './pages/admin/AdminUsage'
import { AdminSystem } from './pages/admin/AdminSystem'
```

2. 将以下占位路由：
```tsx
<Route path="admin/*" element={placeholder('管理后台（Plan 4 实现）')} />
```
替换为嵌套路由树：
```tsx
<Route path="admin/*" element={<AdminLayout />}>
  <Route index element={<AdminUsers />} />
  <Route path="users" element={<AdminUsers />} />
  <Route path="agents" element={<AdminAgents />} />
  <Route path="usage" element={<AdminUsage />} />
  <Route path="system" element={<AdminSystem />} />
</Route>
```

- [ ] **Step 5: 构建验证**

```bash
cd "/d/Desktop/evolution/0 program/8-FinAgentPlantform/frontend/FinAgentPlatform/web" && pnpm build 2>&1 | tail -5
```

Expected: `✓ built in X.XXs`，无错误。

- [ ] **Step 6: Commit**

```bash
cd "/d/Desktop/evolution/0 program/8-FinAgentPlantform/frontend/FinAgentPlatform" && git add web/src/workspace/pages/admin/AdminAgents.tsx web/src/workspace/pages/admin/AdminUsage.tsx web/src/workspace/pages/admin/AdminSystem.tsx web/src/workspace/WorkspaceRouter.tsx && git -c user.email="dev@finagent.local" -c user.name="FinAgent Dev" commit -m "feat(admin): add agent review, usage dashboard, system status and wire admin routes"
```

---

## 自查

**Spec 覆盖：**
- [x] §8.1 AdminLayout：子菜单（用户管理/智能体审核/用量看板/系统状态）+ 返回工作台
- [x] §8.2 用户管理：搜索+筛选 + 表格 + 编辑弹窗（角色/配额）+ 禁用/启用
- [x] §8.3 注册审批：待审批队列置顶 + 激活/拒绝操作 + 激活后加入用户列表
- [x] §8.4 智能体审核：待审核列表 + 查看详情侧抽屉（含完整提示词）+ 通过/拒绝
- [x] §8.5 用量看板：4 张统计卡片 + 用量排行表
- [x] §8.6 系统状态：沙箱池进度条 + 4 个服务状态指示
