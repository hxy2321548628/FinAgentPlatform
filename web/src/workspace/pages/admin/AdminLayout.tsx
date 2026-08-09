import { Outlet } from 'react-router-dom'

export function AdminLayout() {
  return (
    <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
      <Outlet />
    </div>
  )
}
