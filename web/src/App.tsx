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
        {/* 后台只挂一份布局，否则管理员在「账号」与「审核」两组页面间
            切换时会重建侧栏、丢掉用户的折叠状态。ReviewerGuard 负责后台总准入，
            更窄的 AdminGuard 只下沉到账号、用量与系统三个子路由。 */}
        <Route element={<ReviewerGuard />}>
          <Route path="/admin" element={<AdminLayout />}>
            <Route index element={<AdminHome />} />
            <Route path="agents" element={<AdminAgents />} />
            <Route path="skills" element={<AdminSkills />} />
            <Route path="mcp" element={<AdminMcp />} />
            <Route element={<AdminGuard />}>
              <Route path="users" element={<AdminUsers />} />
              <Route path="usage" element={<AdminUsage />} />
              <Route path="system" element={<AdminSystem />} />
            </Route>
            <Route path="*" element={<NotFound title="后台页面不存在" description="该管理页面不存在，或已经被移除。" primaryTo="/admin" primaryLabel="返回后台首页" secondaryTo="/workspace" secondaryLabel="返回工作台" />} />
          </Route>
        </Route>
        <Route element={<AuthGuard />}>
          <Route path="/workspace/*" element={<WorkspaceLayout />}>
            <Route path="*" element={<WorkspaceRouter />} />
          </Route>
        </Route>
        <Route path="*" element={
          <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
            <a className="skip-link" href="#main-content">跳到主要内容</a>
            <Navbar />
            <main id="main-content" tabIndex={-1} style={{ flex: 1 }}>
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
