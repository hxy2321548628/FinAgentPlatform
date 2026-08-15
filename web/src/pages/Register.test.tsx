import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { Register } from './Register'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('Register', () => {
  it('explains that an account without an invite waits for approval', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({
      id: 'student-1', name: '新用户', role: 'student', is_active: false, group_name: null,
    })))

    const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } })
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/register']}>
          <Routes>
            <Route path="/register" element={<Register />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    )

    fireEvent.change(screen.getByPlaceholderText('请输入用户名'), { target: { value: '新用户' } })
    fireEvent.change(screen.getByPlaceholderText('至少 8 位密码'), { target: { value: 'password' } })
    fireEvent.click(screen.getByRole('button', { name: '提交注册申请' }))

    expect((await screen.findByRole('status')).textContent).toContain('请等待管理员审批')
  })

  it('shows the server validation message', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({
      error: { code: 'VALIDATION_ERROR', message: '用户名已存在' },
    }, { status: 422 })))

    const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } })
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/register']}>
          <Routes>
            <Route path="/register" element={<Register />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    )

    fireEvent.change(screen.getByPlaceholderText('请输入用户名'), { target: { value: '已存在' } })
    fireEvent.change(screen.getByPlaceholderText('至少 8 位密码'), { target: { value: 'password' } })
    fireEvent.click(screen.getByRole('button', { name: '提交注册申请' }))

    expect((await screen.findByRole('alert')).textContent).toContain('用户名已存在')
  })
})
