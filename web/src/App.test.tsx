import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
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
vi.mock('./workspace/pages/admin/AdminAgents', () => ({ AdminAgents: () => <div data-testid="admin-agents-page">审核队列</div> }))
vi.mock('./workspace/pages/admin/AdminUsers', () => ({ AdminUsers: () => <div data-testid="admin-users-page">用户管理</div> }))

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

    expect(await screen.findByTestId('admin-agents-page')).toBeTruthy()
    expect(screen.getByTestId('location').textContent).toBe('/admin/agents')
  })

  it('管理员打开 /admin 时仍落到用户管理', async () => {
    mocks.me.mockResolvedValue(ADMIN)

    open('/admin')

    expect(await screen.findByTestId('admin-users-page')).toBeTruthy()
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
    expect(screen.queryByTestId('admin-users-page')).toBeNull()
  })

  it('管理员跨越管理与审核页时保留侧栏状态', async () => {
    mocks.me.mockResolvedValue(ADMIN)

    const { container } = open('/admin/users')

    await screen.findByTestId('admin-users-page')
    const sidebar = container.querySelector('.admin-sidebar')
    expect(sidebar?.classList.contains('collapsed')).toBe(true)

    fireEvent.click(screen.getByRole('button', { name: '展开侧栏' }))
    expect(sidebar?.classList.contains('collapsed')).toBe(false)

    fireEvent.click(screen.getByRole('link', { name: '场景与智能体审核' }))

    expect(await screen.findByTestId('admin-agents-page')).toBeTruthy()
    expect(screen.getByTestId('location').textContent).toBe('/admin/agents')
    expect(container.querySelector('.admin-sidebar')).toBe(sidebar)
    expect(sidebar?.classList.contains('collapsed')).toBe(false)
    expect(screen.getByRole('button', { name: '折叠侧栏' })).toBeTruthy()
  })
})
