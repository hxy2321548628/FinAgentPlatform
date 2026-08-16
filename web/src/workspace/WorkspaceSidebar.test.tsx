import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { AUTH_QUERY_KEY } from '../api/auth'
import { fileKeys } from '../api/files'
import { runKeys } from '../api/runs'
import { threadKeys } from '../api/threads'
import type { Me } from '../api/types'
import { WorkspaceSidebar } from './WorkspaceSidebar'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('WorkspaceSidebar', () => {
  it('keeps cached account data and stays on the page when logout fails', async () => {
    const user: Me = { id: 'teacher-1', name: '张老师', email: 'zhang@zuel.edu.cn', role: 'teacher' }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({
      error: { code: 'INTERNAL', message: '会话服务不可用' },
    }, { status: 503 })))

    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false, staleTime: Number.POSITIVE_INFINITY },
        mutations: { retry: false },
      },
    })
    queryClient.setQueryData(AUTH_QUERY_KEY, user)
    queryClient.setQueryData(threadKeys.detail('thread-1'), { title: '未退出的会话' })
    queryClient.setQueryData(runKeys.detail('run-1'), { content: '仍需保留的结果' })
    queryClient.setQueryData(fileKeys.content('thread-1', 'data.csv'), { text: '仍需保留的数据' })

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/workspace']}>
          <Routes>
            <Route path="/workspace" element={<div data-testid="workspace-route"><WorkspaceSidebar /></div>} />
            <Route path="/login" element={<div data-testid="login-route" />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    )

    fireEvent.click(screen.getByRole('button', { name: /张老师/ }))
    fireEvent.click(screen.getByRole('button', { name: '退出登录' }))

    expect((await screen.findByRole('alert')).textContent).toContain('会话服务不可用')
    expect(screen.getByTestId('workspace-route')).toBeTruthy()
    expect(screen.queryByTestId('login-route')).toBeNull()
    expect(queryClient.getQueryData(AUTH_QUERY_KEY)).toEqual(user)
    expect(queryClient.getQueryData(threadKeys.detail('thread-1'))).toEqual({ title: '未退出的会话' })
    expect(queryClient.getQueryData(runKeys.detail('run-1'))).toEqual({ content: '仍需保留的结果' })
    expect(queryClient.getQueryData(fileKeys.content('thread-1', 'data.csv'))).toEqual({ text: '仍需保留的数据' })

    queryClient.clear()
  })
})
