import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import type { Me } from '../../../api/types'
import { AdminGuard, ReviewerGuard } from './AdminGuard'

const mocks = vi.hoisted(() => ({
  me: vi.fn<() => Promise<Me>>(),
}))

vi.mock('../../../api/auth', async importOriginal => ({
  ...(await importOriginal<typeof import('../../../api/auth')>()),
  me: mocks.me,
}))

afterEach(() => {
  cleanup()
  mocks.me.mockReset()
})

function Location() {
  return <div data-testid="location">{useLocation().pathname}</div>
}

function renderGuard(path: string, guard: 'admin' | 'reviewer' = 'admin') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const Guard = guard === 'admin' ? AdminGuard : ReviewerGuard
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Location />
        <Routes>
          <Route element={<Guard />}>
            <Route path="/admin/*" element={<div>后台内容</div>} />
          </Route>
          <Route path="/login" element={<div>登录页</div>} />
          <Route path="/workspace" element={<div>工作台</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('后台路由守卫', () => {
  it('未登录访问后台时原地显示 404', async () => {
    mocks.me.mockRejectedValue(new Error('未登录'))

    renderGuard('/admin')

    expect(await screen.findByText('404')).toBeTruthy()
    expect(mocks.me).toHaveBeenCalledWith({ redirectOn401: false })
    expect(screen.getByTestId('location').textContent).toBe('/admin')
    expect(screen.queryByText('登录页')).toBeNull()
  })

  it('普通用户访问后台时原地显示 404', async () => {
    mocks.me.mockResolvedValue({ id: 'teacher-1', name: '教师', email: 'teacher@zuel.edu.cn', role: 'teacher' })

    renderGuard('/admin')

    expect(await screen.findByText('404')).toBeTruthy()
    expect(screen.getByTestId('location').textContent).toBe('/admin')
    expect(screen.queryByText('工作台')).toBeNull()
  })

  it('审核员访问管理员页面时原地显示 404', async () => {
    mocks.me.mockResolvedValue({ id: 'reviewer-1', name: '审核员', email: 'reviewer@zuel.edu.cn', role: 'reviewer' })

    renderGuard('/admin/users')

    expect(await screen.findByText('404')).toBeTruthy()
    expect(screen.getByTestId('location').textContent).toBe('/admin/users')
  })

  it('管理员仍可访问管理员页面', async () => {
    mocks.me.mockResolvedValue({ id: 'admin-1', name: '管理员', email: 'admin@zuel.edu.cn', role: 'admin' })

    renderGuard('/admin')

    expect(await screen.findByText('后台内容')).toBeTruthy()
  })

  it('审核员仍可访问审核页面', async () => {
    mocks.me.mockResolvedValue({ id: 'reviewer-1', name: '审核员', email: 'reviewer@zuel.edu.cn', role: 'reviewer' })

    renderGuard('/admin/agents', 'reviewer')

    expect(await screen.findByText('后台内容')).toBeTruthy()
  })
})
