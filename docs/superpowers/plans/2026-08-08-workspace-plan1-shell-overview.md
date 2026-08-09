# 工作台 Plan 1：框架 + 总览页 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 搭建工作台的全屏后台框架（深色 Sidebar + 路由 + 布局），并实现总览页的完整静态 UI。

**Architecture:** 工作台是独立于首页的全屏应用（无顶部 Navbar/Footer），通过 `/workspace/*` 路由挂载。左侧深色 Sidebar 固定，右侧内容区按子路由切换。总览页包含行动建议区、4 张统计卡片、最近会话列表、快速入口。所有数据为静态 mock，无真实接口调用。

**Tech Stack:** React 18 + React Router v7 + TypeScript + CSS Variables（DSD token）· 内联 style，无 Tailwind（工作台沿用现有 theme.css 变量）

---

## 文件结构

```
web/src/
├── workspace/                          ← 新建，工作台所有代码
│   ├── WorkspaceLayout.tsx             ← 全屏框架：Sidebar + 内容区
│   ├── WorkspaceSidebar.tsx            ← 左侧深色导航
│   ├── WorkspaceRouter.tsx             ← 工作台子路由
│   └── pages/
│       └── Overview.tsx                ← 总览页
├── App.tsx                             ← 修改：挂载 /workspace 路由
└── styles/theme.css                    ← 修改：新增工作台 CSS 变量
```

---

### Task 1：theme.css 新增工作台 CSS 变量

**Files:**
- Modify: `web/src/styles/theme.css`

工作台 Sidebar 使用深色背景，需要专属变量。在现有 `:root` 块末尾追加。

- [ ] **Step 1: 在 theme.css 的 `:root` 块内追加工作台变量**

在 `--status-warn: #D97706;` 这行后面追加：

```css
  /* ── Workspace sidebar ── */
  --ws-sidebar-bg:      #0D1829;
  --ws-sidebar-border:  rgba(255,255,255,0.08);
  --ws-sidebar-text:    rgba(255,255,255,0.6);
  --ws-sidebar-active:  rgba(255,255,255,0.95);
  --ws-sidebar-hover:   rgba(255,255,255,0.08);
  --ws-sidebar-accent:  #1e3a5f;
```

- [ ] **Step 2: 验证 dev server 无报错**

```bash
cd web && pnpm dev
```

浏览器打开 `http://localhost:5173`，首页正常渲染即可。

- [ ] **Step 3: Commit**

```bash
git add web/src/styles/theme.css
git -c user.email="dev@finagent.local" -c user.name="FinAgent Dev" commit -m "feat(workspace): add sidebar CSS variables"
```

---

### Task 2：WorkspaceSidebar 组件

**Files:**
- Create: `web/src/workspace/WorkspaceSidebar.tsx`

左侧深色导航，宽 220px，固定不滚动。包含：Logo区、导航项、底部用户信息、返回首页链接。

- [ ] **Step 1: 创建 WorkspaceSidebar.tsx**

```tsx
import { NavLink, useNavigate } from 'react-router-dom'

const LOGO_PATH_1 = 'M24.22,27.73l1.05-2c.36-.69.73-1.38,1.08-2.07a.26.26,0,0,1,.27-.17h3.83a.26.26,0,0,1,.27.18c1.44,3.06,3,6.08,4.65,9a.23.23,0,0,0,.08.16H27.09a.3.3,0,0,1-.32-.19q-1.2-2.34-2.42-4.66l-.14-.25c-.05.09-.1.16-.13.23l-2.44,4.7a.25.25,0,0,1-.26.17H13l.4-.83c1.53-2.72,2.94-5.5,4.27-8.33a.35.35,0,0,1,.38-.24h3.74a.27.27,0,0,1,.28.18l2,3.84Z'
const LOGO_PATH_2 = 'M24.21,4.19a82.908,82.908,0,0,0,2.43,9.16,85.1,85.1,0,0,0,3.43,8.85H18.33a79,79,0,0,0,3.47-8.86,84.311,84.311,0,0,0,2.41-9.15Zm0,16.18A1.3,1.3,0,1,0,23,19.07a1.26,1.26,0,0,0,1.23,1.3Z'

interface NavItem {
  to: string
  label: string
  icon: React.ReactNode
  adminOnly?: boolean
  end?: boolean
}

const NAV_GROUPS: { items: NavItem[] }[] = [
  {
    items: [
      { to: '/workspace', label: '总览', end: true, icon: <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg> },
    ],
  },
  {
    items: [
      { to: '/workspace/chat', label: '分析对话', icon: <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg> },
    ],
  },
  {
    items: [
      { to: '/workspace/scenarios', label: '场景库', icon: <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg> },
      { to: '/workspace/agents', label: '智能体广场', icon: <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="12" cy="8" r="4"/><path d="M20 21a8 8 0 1 0-16 0"/><circle cx="12" cy="8" r="1" fill="currentColor"/></svg> },
    ],
  },
  {
    items: [
      { to: '/workspace/data', label: '我的数据', icon: <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/></svg> },
      { to: '/workspace/my-agents', label: '我的智能体', icon: <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg> },
    ],
  },
  {
    items: [
      { to: '/workspace/admin', label: '管理后台', adminOnly: true, icon: <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg> },
    ],
  },
]

// 原型阶段用 mock，联调时替换为真实 auth
const MOCK_USER = { name: '张老师', role: '教师', isAdmin: false }

function NavItemRow({ item }: { item: NavItem }) {
  return (
    <NavLink
      to={item.to}
      end={item.end}
      style={({ isActive }) => ({
        display: 'flex', alignItems: 'center', gap: 10,
        padding: '9px 16px',
        fontSize: 13, fontWeight: isActive ? 600 : 400,
        color: isActive ? 'var(--ws-sidebar-active)' : 'var(--ws-sidebar-text)',
        background: isActive ? 'var(--ws-sidebar-accent)' : 'transparent',
        borderLeft: isActive ? '3px solid var(--action)' : '3px solid transparent',
        textDecoration: 'none', cursor: 'pointer',
        transition: 'background 0.15s, color 0.15s',
      })}
      onMouseEnter={e => { if (!(e.currentTarget as HTMLElement).style.background.includes('accent')) (e.currentTarget as HTMLElement).style.background = 'var(--ws-sidebar-hover)' }}
      onMouseLeave={e => { const el = e.currentTarget as HTMLElement; if (!el.classList.contains('active')) el.style.background = 'transparent' }}
    >
      <span style={{ flexShrink: 0 }}>{item.icon}</span>
      {item.label}
    </NavLink>
  )
}

export function WorkspaceSidebar() {
  const navigate = useNavigate()
  const user = MOCK_USER

  return (
    <aside style={{
      width: 220, flexShrink: 0,
      background: 'var(--ws-sidebar-bg)',
      display: 'flex', flexDirection: 'column',
      height: '100vh', overflow: 'hidden',
    }}>
      {/* Logo 区 */}
      <div style={{ padding: '18px 16px 14px', borderBottom: '1px solid var(--ws-sidebar-border)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <svg viewBox="12 3 24 34" fill="currentColor" style={{ height: 22, width: 'auto', color: 'var(--logo-red)', flexShrink: 0 }}>
            <path d={LOGO_PATH_1} /><path d={LOGO_PATH_2} />
          </svg>
          <div>
            <div style={{ fontSize: 13, fontWeight: 700, color: '#fff', letterSpacing: '0.02em' }}>FinAgentPlatform</div>
            <div style={{ fontSize: 11, color: 'var(--ws-sidebar-text)', marginTop: 1 }}>工作台</div>
          </div>
        </div>
      </div>

      {/* 导航区 */}
      <nav style={{ flex: 1, overflowY: 'auto', padding: '8px 0' }}>
        {NAV_GROUPS.map((group, gi) => (
          <div key={gi}>
            {gi > 0 && <div style={{ height: 1, background: 'var(--ws-sidebar-border)', margin: '6px 0' }} />}
            {group.items
              .filter(item => !item.adminOnly || user.isAdmin)
              .map(item => <NavItemRow key={item.to} item={item} />)
            }
          </div>
        ))}
      </nav>

      {/* 返回首页 */}
      <div style={{ borderTop: '1px solid var(--ws-sidebar-border)', padding: '8px 0' }}>
        <button
          onClick={() => navigate('/')}
          style={{
            display: 'flex', alignItems: 'center', gap: 10,
            width: '100%', padding: '9px 16px',
            fontSize: 13, color: 'var(--ws-sidebar-text)',
            background: 'none', border: 'none', cursor: 'pointer',
            fontFamily: 'inherit', textAlign: 'left',
          }}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
          返回首页
        </button>
      </div>

      {/* 用户信息 */}
      <div style={{ padding: '12px 16px', borderTop: '1px solid var(--ws-sidebar-border)', display: 'flex', alignItems: 'center', gap: 10 }}>
        <div style={{
          width: 32, height: 32, borderRadius: '50%',
          background: 'var(--action)', color: '#fff',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 13, fontWeight: 700, flexShrink: 0,
        }}>
          {user.name[0]}
        </div>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: '#fff', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{user.name}</div>
          <div style={{ fontSize: 11, color: 'var(--ws-sidebar-text)', marginTop: 1 }}>{user.role}</div>
        </div>
      </div>
    </aside>
  )
}
```

- [ ] **Step 2: 验证文件保存无 TypeScript 报错**

```bash
cd web && pnpm tsc --noEmit 2>&1 | head -20
```

Expected: 无 `WorkspaceSidebar.tsx` 相关错误。

- [ ] **Step 3: Commit**

```bash
git add web/src/workspace/WorkspaceSidebar.tsx
git -c user.email="dev@finagent.local" -c user.name="FinAgent Dev" commit -m "feat(workspace): add WorkspaceSidebar component"
```

---

### Task 3：WorkspaceLayout + WorkspaceRouter + App.tsx 路由接入

**Files:**
- Create: `web/src/workspace/WorkspaceLayout.tsx`
- Create: `web/src/workspace/WorkspaceRouter.tsx`
- Modify: `web/src/App.tsx`

- [ ] **Step 1: 创建 WorkspaceLayout.tsx**

```tsx
import { Outlet } from 'react-router-dom'
import { WorkspaceSidebar } from './WorkspaceSidebar'

export function WorkspaceLayout() {
  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden', background: 'var(--bg)' }}>
      <WorkspaceSidebar />
      <main style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
        <Outlet />
      </main>
    </div>
  )
}
```

- [ ] **Step 2: 创建 WorkspaceRouter.tsx（各子路由的懒加载入口）**

```tsx
import { Routes, Route, Navigate } from 'react-router-dom'
import { Overview } from './pages/Overview'

// 后续 Plan 2/3/4 的页面在此追加 import
// import { Chat } from './pages/Chat'
// import { Scenarios } from './pages/AgentScenarios'

export function WorkspaceRouter() {
  return (
    <Routes>
      <Route index element={<Overview />} />
      {/* 以下路由在后续 Plan 中逐步添加 */}
      <Route path="chat" element={<div style={{ padding: 40, color: 'var(--text-secondary)' }}>分析对话（Plan 2 实现）</div>} />
      <Route path="chat/:threadId" element={<div style={{ padding: 40, color: 'var(--text-secondary)' }}>分析对话（Plan 2 实现）</div>} />
      <Route path="scenarios" element={<div style={{ padding: 40, color: 'var(--text-secondary)' }}>场景库（Plan 3 实现）</div>} />
      <Route path="agents" element={<div style={{ padding: 40, color: 'var(--text-secondary)' }}>智能体广场（Plan 3 实现）</div>} />
      <Route path="agents/new" element={<div style={{ padding: 40, color: 'var(--text-secondary)' }}>发布智能体（Plan 3 实现）</div>} />
      <Route path="data" element={<div style={{ padding: 40, color: 'var(--text-secondary)' }}>我的数据（Plan 3 实现）</div>} />
      <Route path="my-agents" element={<div style={{ padding: 40, color: 'var(--text-secondary)' }}>我的智能体（Plan 3 实现）</div>} />
      <Route path="admin/*" element={<div style={{ padding: 40, color: 'var(--text-secondary)' }}>管理后台（Plan 4 实现）</div>} />
      <Route path="*" element={<Navigate to="/workspace" replace />} />
    </Routes>
  )
}
```

- [ ] **Step 3: 修改 App.tsx 挂载 /workspace 路由**

将 App.tsx 完整替换为：

```tsx
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { Navbar } from './components/Navbar'
import { Footer } from './components/Footer'
import { Home } from './pages/Home'
import { Scenarios } from './pages/Scenarios'
import { Capabilities } from './pages/Capabilities'
import { DataAssets } from './pages/DataAssets'
import { Login } from './pages/Login'
import { Settings } from './pages/Settings'
import { WorkspaceLayout } from './workspace/WorkspaceLayout'
import { WorkspaceRouter } from './workspace/WorkspaceRouter'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* 登录页：无 Navbar/Footer */}
        <Route path="/login" element={<Login />} />

        {/* 工作台：独立全屏布局 */}
        <Route path="/workspace/*" element={<WorkspaceLayout />}>
          <Route path="*" element={<WorkspaceRouter />} />
        </Route>

        {/* 首页及导航页：带 Navbar/Footer */}
        <Route path="*" element={
          <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
            <Navbar />
            <main style={{ flex: 1 }}>
              <Routes>
                <Route path="/" element={<Home />} />
                <Route path="/scenarios" element={<Scenarios />} />
                <Route path="/capabilities" element={<Capabilities />} />
                <Route path="/data" element={<DataAssets />} />
                <Route path="/settings" element={<Settings />} />
              </Routes>
            </main>
            <Footer />
          </div>
        } />
      </Routes>
    </BrowserRouter>
  )
}
```

- [ ] **Step 4: 创建 workspace/pages/ 目录占位（确保 Overview.tsx 路径可用）**

创建目录（直接在 Step 5 创建文件即可，不需要额外操作）。

- [ ] **Step 5: 验证路由跳转**

```bash
cd web && pnpm dev
```

- 访问 `http://localhost:5173/workspace` → 应看到深色 Sidebar + 右侧空白内容区
- 访问 `http://localhost:5173/workspace/chat` → 应看到 Sidebar + 「分析对话（Plan 2 实现）」占位文字
- 访问 `http://localhost:5173/` → 首页正常，有 Navbar/Footer
- 访问 `http://localhost:5173/login` → 登录页正常，无 Navbar

- [ ] **Step 6: Commit**

```bash
git add web/src/workspace/ web/src/App.tsx
git -c user.email="dev@finagent.local" -c user.name="FinAgent Dev" commit -m "feat(workspace): wire up workspace layout and router"
```

---

### Task 4：总览页 — 统计卡片 + 行动建议

**Files:**
- Create: `web/src/workspace/pages/Overview.tsx`

- [ ] **Step 1: 创建 Overview.tsx（上半部分：页头 + 行动建议 + 统计卡片）**

```tsx
import { useNavigate } from 'react-router-dom'

// ── mock 数据，联调时替换为 API 调用 ──────────────────────
const MOCK_STATE = {
  hasRunningRun: true,
  runningTitle: '新能源行业波动率分析',
  runningElapsed: '2m14s',
  tokenUsed: 97200,
  tokenQuota: 120000,
  monthlyRuns: 12,
  outputFiles: 34,
  agentCalls: 9,
}

const MOCK_SESSIONS = [
  { id: '1', title: '新能源行业波动率分析', time: '进行中', status: 'running' as const, tokens: 12430 },
  { id: '2', title: 'A 股收益归因分解', time: '昨天 14:32', status: 'done' as const, tokens: 31340 },
  { id: '3', title: '基金最大回撤计算', time: '2 天前', status: 'done' as const, tokens: 8920 },
  { id: '4', title: 'Fama-French 三因子复现', time: '3 天前', status: 'done' as const, tokens: 45230 },
  { id: '5', title: '持仓集中度风险分析', time: '4 天前', status: 'failed' as const, tokens: 3210 },
]
// ─────────────────────────────────────────────────────────────

const STATUS_COLOR = {
  running: 'var(--action)',
  done: 'var(--status-done)',
  failed: '#DC2626',
} as const

const STATUS_LABEL = {
  running: '◉ 运行中',
  done: '✓ 完成',
  failed: '✗ 失败',
} as const

function StatCard({ label, value, unit, pct }: { label: string; value: string; unit: string; pct?: number }) {
  return (
    <div style={{
      background: 'var(--surface)', border: '1px solid var(--border)',
      borderRadius: 10, padding: '18px 20px',
    }}>
      <div style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.12em', color: 'var(--text-muted)', fontFamily: "'JetBrains Mono', monospace", marginBottom: 8 }}>{label}</div>
      <div style={{ fontSize: 26, fontWeight: 800, color: 'var(--text-primary)', fontFamily: "'JetBrains Mono', monospace", lineHeight: 1, marginBottom: 4 }}>{value}</div>
      <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{unit}</div>
      {pct !== undefined && (
        <div style={{ marginTop: 10, height: 4, background: 'var(--border-light)', borderRadius: 2, overflow: 'hidden' }}>
          <div style={{ height: '100%', width: `${pct}%`, background: pct > 80 ? 'var(--status-warn)' : 'var(--action)', borderRadius: 2, transition: 'width 0.4s' }} />
        </div>
      )}
    </div>
  )
}

function ActionBanner() {
  const navigate = useNavigate()
  const { hasRunningRun, runningTitle, runningElapsed, tokenUsed, tokenQuota } = MOCK_STATE
  const pct = Math.round(tokenUsed / tokenQuota * 100)

  if (hasRunningRun) {
    return (
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        background: 'var(--action-light)', border: '1px solid var(--action-border)',
        borderLeft: '4px solid var(--action)',
        borderRadius: 8, padding: '14px 20px', marginBottom: 20,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ color: 'var(--action)', fontSize: 14, fontWeight: 600 }}>◉</span>
          <div>
            <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>分析进行中</span>
            <span style={{ fontSize: 13, color: 'var(--text-secondary)', marginLeft: 10 }}>{runningTitle} · 已用时 {runningElapsed}</span>
          </div>
        </div>
        <button
          onClick={() => navigate('/workspace/chat/1')}
          style={{ padding: '7px 16px', background: 'var(--action)', color: '#fff', border: 'none', borderRadius: 6, fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}
        >
          查看进度 →
        </button>
      </div>
    )
  }

  if (pct > 80) {
    return (
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        background: '#FFFBEB', border: '1px solid #FDE68A',
        borderLeft: '4px solid var(--status-warn)',
        borderRadius: 8, padding: '14px 20px', marginBottom: 20,
      }}>
        <span style={{ fontSize: 14, color: '#92400E' }}>⚠️ 本月 token 已用 {pct}%，剩余 {((tokenQuota - tokenUsed) / 1000).toFixed(0)}K</span>
        <button
          onClick={() => navigate('/settings')}
          style={{ padding: '7px 16px', background: 'transparent', color: '#92400E', border: '1px solid #FDE68A', borderRadius: 6, fontSize: 13, cursor: 'pointer', fontFamily: 'inherit' }}
        >
          查看用量 →
        </button>
      </div>
    )
  }

  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      background: 'var(--bg)', border: '1px solid var(--border)',
      borderLeft: '4px solid var(--border)',
      borderRadius: 8, padding: '14px 20px', marginBottom: 20,
    }}>
      <span style={{ fontSize: 14, color: 'var(--text-secondary)' }}>从场景库开始你的下一次分析</span>
      <button
        onClick={() => navigate('/workspace/scenarios')}
        style={{ padding: '7px 16px', background: 'var(--action)', color: '#fff', border: 'none', borderRadius: 6, fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}
      >
        浏览场景库 →
      </button>
    </div>
  )
}

export function Overview() {
  const navigate = useNavigate()
  const { tokenUsed, tokenQuota, monthlyRuns, outputFiles, agentCalls } = MOCK_STATE
  const tokenPct = Math.round(tokenUsed / tokenQuota * 100)

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '32px 36px', background: 'var(--bg)' }}>
      {/* 页头 */}
      <div style={{ marginBottom: 24 }}>
        <div style={{ fontSize: 10, fontFamily: "'JetBrains Mono', monospace", textTransform: 'uppercase', letterSpacing: '0.3em', color: 'var(--text-muted)', marginBottom: 6 }}>
          // OVERVIEW
        </div>
        <h1 style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)' }}>总览</h1>
        <p style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 4 }}>
          {new Date().toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric', weekday: 'long' })}
        </p>
      </div>

      {/* 行动建议 */}
      <ActionBanner />

      {/* 统计卡片 */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14, marginBottom: 28 }}>
        <StatCard label="本月分析" value={String(monthlyRuns)} unit="次 run" />
        <StatCard label="Token 消耗" value={`${(tokenUsed / 1000).toFixed(0)}K`} unit={`/ ${tokenQuota / 1000}K tokens`} pct={tokenPct} />
        <StatCard label="产出文件" value={String(outputFiles)} unit="个文件" />
        <StatCard label="Agent 调用" value={String(agentCalls)} unit="次（我发布的）" />
      </div>

      {/* 下半部分：最近会话 + 快速入口 */}
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 20 }}>

        {/* 最近会话 */}
        <div>
          <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 12 }}>最近会话</div>
          <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, overflow: 'hidden' }}>
            {MOCK_SESSIONS.map((session, i) => (
              <div
                key={session.id}
                onClick={() => navigate(`/workspace/chat/${session.id}`)}
                style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  padding: '12px 16px',
                  borderBottom: i < MOCK_SESSIONS.length - 1 ? '1px solid var(--border-light)' : 'none',
                  cursor: 'pointer', transition: 'background 0.15s',
                }}
                onMouseEnter={e => (e.currentTarget as HTMLElement).style.background = 'var(--bg)'}
                onMouseLeave={e => (e.currentTarget as HTMLElement).style.background = 'transparent'}
              >
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', marginBottom: 3 }}>
                    {session.title}
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: "'JetBrains Mono', monospace" }}>
                    {session.time} · {(session.tokens / 1000).toFixed(1)}K tokens
                  </div>
                </div>
                <span style={{ fontSize: 11, fontWeight: 600, color: STATUS_COLOR[session.status], marginLeft: 16, flexShrink: 0 }}>
                  {STATUS_LABEL[session.status]}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* 快速入口 */}
        <div>
          <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 12 }}>快速入口</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {[
              { label: '新建分析对话', desc: '直接描述需求，智能体开始工作', to: '/workspace/chat', icon: '💬' },
              { label: '浏览场景库', desc: '从预设分析场景快速启动', to: '/workspace/scenarios', icon: '🗂' },
              { label: '上传数据文件', desc: 'CSV、Excel、PDF 上传至工作区', to: '/workspace/data', icon: '📁' },
            ].map(item => (
              <div
                key={item.to}
                onClick={() => navigate(item.to)}
                style={{
                  background: 'var(--surface)', border: '1px solid var(--border)',
                  borderRadius: 8, padding: '14px 16px', cursor: 'pointer',
                  transition: 'border-color 0.2s, box-shadow 0.2s',
                }}
                onMouseEnter={e => { (e.currentTarget as HTMLElement).style.borderColor = 'var(--action-border)'; (e.currentTarget as HTMLElement).style.boxShadow = '0 2px 8px rgba(23,73,196,0.08)' }}
                onMouseLeave={e => { (e.currentTarget as HTMLElement).style.borderColor = 'var(--border)'; (e.currentTarget as HTMLElement).style.boxShadow = 'none' }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                  <span style={{ fontSize: 16 }}>{item.icon}</span>
                  <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>{item.label}</span>
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-muted)', paddingLeft: 24 }}>{item.desc}</div>
              </div>
            ))}
          </div>
        </div>

      </div>
    </div>
  )
}
```

- [ ] **Step 2: 验证总览页渲染**

```bash
cd web && pnpm dev
```

访问 `http://localhost:5173/workspace`，检查：
- Sidebar 左侧深色，导航项正常高亮「总览」
- 行动建议横幅显示「分析进行中」（因 `MOCK_STATE.hasRunningRun = true`）
- 4 张统计卡片排成一行
- 最近会话列表 5 条，hover 有背景色变化
- 快速入口 3 张卡片，hover 有边框变化
- 点击导航项「场景库」→ 显示占位文字

- [ ] **Step 3: 验证构建**

```bash
cd web && pnpm build 2>&1 | tail -5
```

Expected: `✓ built in X.XXs`，无 TypeScript 错误。

- [ ] **Step 4: Commit**

```bash
git add web/src/workspace/
git -c user.email="dev@finagent.local" -c user.name="FinAgent Dev" commit -m "feat(workspace): implement overview page with stats and action banner"
```

---

### Task 5：Navbar 接入「进入工作台」链接

**Files:**
- Modify: `web/src/components/Navbar.tsx`

当前 Navbar 中「进入工作台」是 `href="#workspace"` 占位，需改为真实路由。

- [ ] **Step 1: 修改 Navbar.tsx 中「进入工作台」链接**

找到以下行：
```tsx
<a href="#workspace" style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '8px 12px', borderRadius: 7, fontSize: 13, color: 'var(--text-primary)', textDecoration: 'none', fontWeight: 600 }}>
  进入工作台 →
</a>
```

替换为：
```tsx
<NavLink to="/workspace" onClick={() => setOpen(false)} style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '8px 12px', borderRadius: 7, fontSize: 13, color: 'var(--text-primary)', textDecoration: 'none', fontWeight: 600 }}>
  进入工作台 →
</NavLink>
```

- [ ] **Step 2: 验证跳转**

访问首页，点击头像 → 点击「进入工作台」→ 应进入 `/workspace` 工作台总览页。

- [ ] **Step 3: Commit**

```bash
git add web/src/components/Navbar.tsx
git -c user.email="dev@finagent.local" -c user.name="FinAgent Dev" commit -m "feat(workspace): wire up 'enter workspace' link in navbar"
```

---

## 自查清单

**Spec 覆盖检查：**
- [x] §1.1 路由规划 — WorkspaceRouter.tsx 覆盖所有路由（含占位）
- [x] §1.2 左侧导航结构 — WorkspaceSidebar.tsx 包含所有菜单项
- [x] §2.1 总览页结构 — 行动建议 + 统计卡片 + 最近会话 + 快速入口
- [x] §2.2 行动建议 — 运行中、token 超 80%、正常三种状态
- [x] §2.3 统计卡片 — 4 列，含 token 进度条
- [x] §2.4 最近会话 — 5 条，含状态徽标
- [x] §2.5 快速入口 — 3 个入口卡片
- [x] Navbar「进入工作台」接入真实路由
- [x] 工作台无顶部 Navbar/Footer

**无 placeholder — 所有步骤含完整代码。**

**类型一致性 — `MOCK_STATE`、`MOCK_SESSIONS`、`STATUS_COLOR`、`STATUS_LABEL` 在 Overview.tsx 内部定义，无跨文件依赖。**
