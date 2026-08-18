import { Outlet } from 'react-router-dom'
import { WorkspaceSidebar } from './WorkspaceSidebar'

export function WorkspaceLayout() {
  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden', background: 'var(--bg)' }}>
      <a className="skip-link" href="#workspace-main">跳到主要内容</a>
      <WorkspaceSidebar />
      <main id="workspace-main" className="page-grid-surface" tabIndex={-1} style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
        <Outlet />
      </main>
    </div>
  )
}
