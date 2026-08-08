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
