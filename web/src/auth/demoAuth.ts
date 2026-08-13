const DEMO_ADMIN_SESSION_KEY = 'zuel-demo-admin'

export function loginDemoAdmin(name: string, password: string): boolean {
  if (name !== 'admin' || password !== 'zuel-admin-dev') return false
  sessionStorage.setItem(DEMO_ADMIN_SESSION_KEY, 'true')
  return true
}

export function isDemoAdmin(): boolean {
  return sessionStorage.getItem(DEMO_ADMIN_SESSION_KEY) === 'true'
}

export function clearDemoAuth(): void {
  sessionStorage.removeItem(DEMO_ADMIN_SESSION_KEY)
}
