import { useEffect, useState } from 'react'
import { Navigate, Outlet } from 'react-router-dom'
import { clearDemoAuth, isDemoAdmin } from '../../../auth/demoAuth'

type Access = 'checking' | 'allowed' | 'denied'

export function AdminGuard() {
  const [access, setAccess] = useState<Access>('checking')

  useEffect(() => {
    const check = async () => {
      try {
        const response = await fetch('/api/auth/me', { credentials: 'include' })
        if (response.ok) {
          const user = await response.json() as { role: string }
          clearDemoAuth()
          setAccess(user.role === 'admin' ? 'allowed' : 'denied')
          return
        }
        if (response.status === 401 || response.status === 403) {
          clearDemoAuth()
          setAccess('denied')
          return
        }
        setAccess(isDemoAdmin() ? 'allowed' : 'denied')
      } catch {
        setAccess(isDemoAdmin() ? 'allowed' : 'denied')
      }
    }
    void check()
  }, [])

  if (access === 'checking') return <div style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', color: 'var(--text-muted)' }}>正在验证管理员权限…</div>
  if (access === 'denied') return <Navigate to="/workspace" replace />
  return <Outlet />
}
