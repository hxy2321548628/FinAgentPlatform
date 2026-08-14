import { AuthGuard } from '../../../auth/AuthGuard'

export function AdminGuard() {
  return <AuthGuard roles={['admin']} />
}
