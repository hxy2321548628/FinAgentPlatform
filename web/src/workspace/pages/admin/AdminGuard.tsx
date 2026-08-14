import { AuthGuard } from '../../../auth/AuthGuard'

/**
 * 管理后台的准入：账号、配额、系统状态那几页。
 *
 * **`reviewer` 进不来。** 它只有审核那一页 —— 一旦让它顺手多拿一样，
 * 这个角色就退化成 `admin` 的别名。
 */
export function AdminGuard() {
  return <AuthGuard roles={['admin']} />
}

/** 审核页的准入。`admin` 同时满足，反过来不成立。 */
export function ReviewerGuard() {
  return <AuthGuard roles={['admin', 'reviewer']} />
}
