import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { Navbar } from './components/Navbar'
import { Footer } from './components/Footer'
import { NotFound } from './components/NotFound'
import { Home } from './pages/Home'
import { Marketplace } from './pages/Marketplace'
import { Scenarios } from './pages/Scenarios'
import { Capabilities } from './pages/Capabilities'
import { DataAssets } from './pages/DataAssets'
import { Login } from './pages/Login'
import { Register } from './pages/Register'
import { AuthGuard } from './auth/AuthGuard'
import { WorkspaceLayout } from './workspace/WorkspaceLayout'
import { WorkspaceRouter } from './workspace/WorkspaceRouter'
import { AdminGuard, AdminHome, ReviewerGuard } from './workspace/pages/admin/AdminGuard'
import { AdminLayout } from './workspace/pages/admin/AdminLayout'
import { AdminUsers } from './workspace/pages/admin/AdminUsers'
import { AdminAgents } from './workspace/pages/admin/AdminAgents'
import { AdminMcp, AdminSkills } from './workspace/pages/admin/AdminCapabilities'
import { AdminUsage } from './workspace/pages/admin/AdminUsage'
import { AdminSystem } from './workspace/pages/admin/AdminSystem'

export default function App() {
  return (
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  )
}

/**
 * 路由表本身，不含 `BrowserRouter`。
 *
 * 拆出来是为了让测试能在 `MemoryRouter` 里跑**这一份**路由表 —— 在测试里另搭一份
 * 等于什么都没验：`/admin` 落到哪个守卫手上，取决于这些 `Route` 的排布本身。
 */
export function AppRoutes() {
  return (
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        {/* **审核与管理是两道准入。** `reviewer` 只进得来 Agent 与 Skill 两个审核页，
            账号与配额等管理页仍然只有 admin 打得开。

            **裸 `/admin` 的 index 必须挂在这一块（宽的那道）里。** 挂到 AdminGuard
            下面的话，reviewer 打开 `/admin` 撞的是管理员守卫 —— 得到 404，
            看起来就是「审核员进不去后台」。落到哪一页由 AdminHome 按角色分。 */}
        <Route element={<ReviewerGuard />}>
          <Route path="/admin" element={<AdminLayout />}>
            <Route index element={<AdminHome />} />
            <Route path="agents" element={<AdminAgents />} />
            <Route path="skills" element={<AdminSkills />} />
            <Route path="mcp" element={<AdminMcp />} />
          </Route>
        </Route>
        <Route element={<AdminGuard />}>
          <Route path="/admin" element={<AdminLayout />}>
            <Route path="users" element={<AdminUsers />} />
            <Route path="usage" element={<AdminUsage />} />
            <Route path="system" element={<AdminSystem />} />
            <Route path="*" element={<NotFound title="后台页面不存在" description="该管理页面不存在，或已经被移除。" primaryTo="/admin/users" primaryLabel="返回用户管理" secondaryTo="/workspace" secondaryLabel="返回工作台" />} />
          </Route>
        </Route>
        <Route element={<AuthGuard />}>
          <Route path="/workspace/*" element={<WorkspaceLayout />}>
            <Route path="*" element={<WorkspaceRouter />} />
          </Route>
        </Route>
        <Route path="*" element={
          <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
            <Navbar />
            <main style={{ flex: 1 }}>
              <Routes>
                <Route path="/" element={<Home />} />
                <Route path="/marketplace" element={<Marketplace />} />
                <Route path="/scenarios" element={<Scenarios />} />
                <Route path="/capabilities" element={<Capabilities />} />
                <Route path="/data" element={<DataAssets />} />
                <Route path="*" element={<NotFound primaryTo="/" primaryLabel="返回首页" secondaryTo="/workspace" secondaryLabel="进入工作台" />} />
              </Routes>
            </main>
            <Footer />
          </div>
        } />
      </Routes>
  )
}
