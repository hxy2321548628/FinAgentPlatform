import { useQuery } from '@tanstack/react-query'
import { Outlet } from 'react-router-dom'
import { AUTH_QUERY_KEY, me } from '../../../api/auth'
import type { UserRole } from '../../../api/types'
import { NotFound } from '../../../components/NotFound'

const notFound = (
  <NotFound
    primaryTo="/"
    primaryLabel="返回首页"
    secondaryTo="/workspace"
    secondaryLabel="进入工作台"
  />
)

function BackendGuard({ roles }: { roles: readonly UserRole[] }) {
  const current = useQuery({
    queryKey: AUTH_QUERY_KEY,
    queryFn: () => me({ redirectOn401: false }),
  })

  if (current.isPending) {
    return <div style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', color: 'var(--text-muted)' }}>正在验证登录状态…</div>
  }
  if (current.isError || !current.data || !roles.includes(current.data.role)) return notFound
  return <Outlet />
}

/**
 * 管理后台的准入：账号、配额、系统状态那几页。
 *
 * **`reviewer` 进不来。** 它只有审核那一页 —— 一旦让它顺手多拿一样，
 * 这个角色就退化成 `admin` 的别名。
 */
export function AdminGuard() {
  return <BackendGuard roles={['admin']} />
}

/** 审核页的准入。`admin` 同时满足，反过来不成立。 */
export function ReviewerGuard() {
  return <BackendGuard roles={['admin', 'reviewer']} />
}
