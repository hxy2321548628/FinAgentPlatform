import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, useLocation } from 'react-router-dom'
import type { Me } from './api/types'
import { AppRoutes } from './App'

/**
 * **这一组挡的是「审核员进不去后台」。**
 *
 * 路由表本身是对的 —— `/admin/agents` 一直放 reviewer 进。漏的是**落点**：
 * 裸 `/admin` 的 index 挂在 AdminGuard 那一块里，于是 reviewer 打开 `/admin`
 * 撞的是管理员守卫，得到 404。而登录后又只有 admin 会被送进后台，
 * 侧边栏也没有入口 —— 三处叠起来，审核员实际上没有任何一条路进得去。
 *
 * 单独测守卫看不出这个：`AdminGuard.test.tsx` 里每条都过，因为它测的是
 * 「守卫放不放行」，而这里坏的是「哪一个守卫接住了这个路径」。所以这一组
 * 必须跑**真实的路由表**，不能在测试里另搭一份。
 */

const mocks = vi.hoisted(() => ({
  me: vi.fn<() => Promise<Me>>(),
}))

vi.mock('./api/auth', async importOriginal => ({
  ...(await importOriginal<typeof import('./api/auth')>()),
  me: mocks.me,
}))

// 页面本身不是这一组要测的东西，换成认得出的桩，免得把它们的数据请求也拖进来
vi.mock('./workspace/pages/admin/AdminAgents', () => ({ AdminAgents: () => <div>审核队列</div> }))
vi.mock('./workspace/pages/admin/AdminUsers', () => ({ AdminUsers: () => <div>用户管理</div> }))
// 布局自己也有一份按角色过滤的导航，标签文字会和上面的页面桩撞车。
// 这一组测的是「哪个守卫接住了这个路径」，把布局换成一个纯粹的 Outlet
vi.mock('./workspace/pages/admin/AdminLayout', async () => {
  const { Outlet } = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return { AdminLayout: () => <Outlet /> }
})

afterEach(() => {
  cleanup()
  mocks.me.mockReset()
})

function Location() {
  return <div data-testid="location">{useLocation().pathname}</div>
}

function open(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Location />
        <AppRoutes />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const REVIEWER: Me = { id: 'reviewer-1', name: '审核员', email: 'reviewer@zuel.edu.cn', role: 'reviewer' }
const ADMIN: Me = { id: 'admin-1', name: '管理员', email: 'admin@zuel.edu.cn', role: 'admin' }

describe('后台落点', () => {
  it('审核员打开 /admin 时落到审核队列，而不是 404', async () => {
    mocks.me.mockResolvedValue(REVIEWER)

    open('/admin')

    expect(await screen.findByText('审核队列')).toBeTruthy()
    expect(screen.getByTestId('location').textContent).toBe('/admin/agents')
  })

  it('管理员打开 /admin 时仍落到用户管理', async () => {
    mocks.me.mockResolvedValue(ADMIN)

    open('/admin')

    expect(await screen.findByText('用户管理')).toBeTruthy()
    expect(screen.getByTestId('location').textContent).toBe('/admin/users')
  })

  it('教师打开 /admin 仍是 404，分流没有变成一道后门', async () => {
    mocks.me.mockResolvedValue({ id: 'teacher-1', name: '教师', email: 't@zuel.edu.cn', role: 'teacher' })

    open('/admin')

    expect(await screen.findByText('404')).toBeTruthy()
  })

  it('审核员打开 /admin/users 仍是 404', async () => {
    mocks.me.mockResolvedValue(REVIEWER)

    open('/admin/users')

    expect(await screen.findByText('404')).toBeTruthy()
    expect(screen.queryByText('用户管理')).toBeNull()
  })
})
