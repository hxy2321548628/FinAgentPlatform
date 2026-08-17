import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { AdminLayout } from './AdminLayout'

const mocks = vi.hoisted(() => ({
  me: vi.fn(async () => ({ id: 'reviewer-1', name: '审核老师', email: 'reviewer@zuel.edu.cn', role: 'reviewer' as const })),
}))

vi.mock('../../../api/auth', async importOriginal => ({
  ...(await importOriginal<typeof import('../../../api/auth')>()),
  me: mocks.me,
}))

afterEach(() => { cleanup(); mocks.me.mockClear() })

describe('AdminLayout', () => {
  /**
   * reviewer 看得到三个审核入口（agent / skill / MCP，2026-08-16 起 MCP 也归它审），
   * 看不到账号、用量与系统状态 —— 那三样是运维，交出去这个角色就成了 admin 的别名。
   */
  it('reviewer 只看得到审核相关的三个入口', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/admin/agents']}>
          <Routes>
            <Route path="/admin" element={<AdminLayout />}>
              <Route path="agents" element={<div>审核内容</div>} />
            </Route>
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    )

    expect(await screen.findByText('审核老师')).toBeTruthy()
    expect(screen.getByRole('link', { name: '场景与智能体审核' })).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Skill 管理' })).toBeTruthy()
    expect(screen.getByRole('link', { name: 'MCP 管理' })).toBeTruthy()
    expect(screen.queryByRole('link', { name: '用户管理' })).toBeNull()
    expect(screen.queryByRole('link', { name: '用量看板' })).toBeNull()
    expect(screen.queryByRole('link', { name: '系统状态' })).toBeNull()
  })

  it('默认折叠侧栏，并允许像工作台一样展开', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const { container } = render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/admin/agents']}>
          <Routes>
            <Route path="/admin" element={<AdminLayout />}>
              <Route path="agents" element={<div>审核内容</div>} />
            </Route>
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    )

    await screen.findByText('审核老师')
    const toggle = screen.getByRole('button', { name: '展开侧栏' })
    expect(container.querySelector('.admin-sidebar')?.classList.contains('collapsed')).toBe(true)

    fireEvent.click(toggle)

    expect(screen.getByRole('button', { name: '折叠侧栏' })).toBeTruthy()
    expect(container.querySelector('.admin-sidebar')?.classList.contains('collapsed')).toBe(false)
  })
})
