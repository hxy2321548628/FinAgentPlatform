import { useQuery } from '@tanstack/react-query'
import { Navigate, Outlet } from 'react-router-dom'
import { AUTH_QUERY_KEY, me } from '../api/auth'
import type { UserRole } from '../api/types'

export function AuthGuard({ roles }: { roles?: readonly UserRole[] }) {
  const current = useQuery({ queryKey: AUTH_QUERY_KEY, queryFn: () => me() })

  if (current.isPending) {
    return <div style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', color: 'var(--text-muted)' }}>正在验证登录状态…</div>
  }
  if (current.isError || !current.data) return <Navigate to="/login" replace />
  if (roles && !roles.includes(current.data.role)) return <Navigate to="/workspace" replace />
  return <Outlet />
}
