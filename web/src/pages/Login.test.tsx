import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { AUTH_QUERY_KEY } from '../api/auth'
import { fileKeys } from '../api/files'
import { runKeys } from '../api/runs'
import { threadKeys } from '../api/threads'
import type { Me } from '../api/types'
import { Login } from './Login'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('Login', () => {
  it('clears the previous account cache before storing the new identity', async () => {
    const previousUser: Me = { id: 'old-user', name: '旧账号', role: 'teacher' }
    const newUser: Me = { id: 'new-user', name: '新账号', role: 'teacher' }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json(newUser)))

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
    queryClient.setQueryData(AUTH_QUERY_KEY, previousUser)
    queryClient.setQueryData(threadKeys.detail('thread-old'), { title: '旧会话' })
    queryClient.setQueryData(runKeys.detail('run-old'), { content: '敏感分析结果' })
    queryClient.setQueryData(fileKeys.content('thread-old', 'secret.csv'), { text: '敏感数据' })
    const clear = vi.spyOn(queryClient, 'clear')
    const setQueryData = vi.spyOn(queryClient, 'setQueryData')

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/login']}>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/workspace" element={<div data-testid="workspace-route" />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    )

    fireEvent.change(screen.getByPlaceholderText('请输入用户名'), { target: { value: '新账号' } })
    fireEvent.change(screen.getByPlaceholderText('请输入密码'), { target: { value: 'password' } })
    fireEvent.click(screen.getByRole('button', { name: '登录系统' }))

    await screen.findByTestId('workspace-route')
    await waitFor(() => expect(clear).toHaveBeenCalledOnce())
    expect(queryClient.getQueryData(threadKeys.detail('thread-old'))).toBeUndefined()
    expect(queryClient.getQueryData(runKeys.detail('run-old'))).toBeUndefined()
    expect(queryClient.getQueryData(fileKeys.content('thread-old', 'secret.csv'))).toBeUndefined()
    expect(queryClient.getQueryData(AUTH_QUERY_KEY)).toEqual(newUser)
    expect(setQueryData).toHaveBeenCalledWith(AUTH_QUERY_KEY, newUser)
    expect(clear.mock.invocationCallOrder[0]).toBeLessThan(setQueryData.mock.invocationCallOrder.at(-1)!)

    queryClient.clear()
  })
})
