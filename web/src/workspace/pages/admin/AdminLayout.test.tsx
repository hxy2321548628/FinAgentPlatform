import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen } from '@testing-library/react'
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
  it('reviewer 只看得到审核相关的两个入口', async () => {
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
    expect(screen.queryByRole('link', { name: '用户管理' })).toBeNull()
    expect(screen.queryByRole('link', { name: 'MCP 管理' })).toBeNull()
  })
})
