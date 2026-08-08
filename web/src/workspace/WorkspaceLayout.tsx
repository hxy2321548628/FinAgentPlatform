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
