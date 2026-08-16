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

    fireEvent.keyDown(screen.getByRole('button', { name: /用户菜单：张老师/ }), { key: 'ArrowDown' })
    fireEvent.click(screen.getByRole('menuitem', { name: '退出登录' }))

    expect((await screen.findByRole('alert')).textContent).toContain('会话服务不可用')
    expect(screen.getByTestId('workspace-route')).toBeTruthy()
    expect(screen.queryByTestId('login-route')).toBeNull()
    expect(queryClient.getQueryData(AUTH_QUERY_KEY)).toEqual(user)
    expect(queryClient.getQueryData(threadKeys.detail('thread-1'))).toEqual({ title: '未退出的会话' })
    expect(queryClient.getQueryData(runKeys.detail('run-1'))).toEqual({ content: '仍需保留的结果' })
    expect(queryClient.getQueryData(fileKeys.content('thread-1', 'data.csv'))).toEqual({ text: '仍需保留的数据' })

    queryClient.clear()
  })

  /**
   * **后台入口原来一处都没有。** admin 靠登录那一跳进后台，一旦点了「返回工作台」
   * 就没有路回去；reviewer 连那一跳都没有 —— 除非手输 URL，否则进不去审核队列。
   *
   * 落点必须按角色分：reviewer 打不开 `/admin/users`，指过去等于指进一个 404。
   */
  it.each([
    { role: 'admin' as const, to: '/admin/users' },
    { role: 'reviewer' as const, to: '/admin/agents' },
  ])('给 $role 一个后台入口，指向 $to', ({ role, to }) => {
    expect(entryHref({ id: 'u1', name: '某人', email: 'a@zuel.edu.cn', role })).toBe(to)
  })

  it.each(['teacher', 'student'] as const)('%s 看不到后台入口', role => {
    expect(entryHref({ id: 'u1', name: '某人', email: 'a@zuel.edu.cn', role })).toBeNull()
  })

  it('侧栏可折叠为图标栏并恢复（P2-2）', () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: Number.POSITIVE_INFINITY } },
    })
    queryClient.setQueryData(AUTH_QUERY_KEY, { id: 'u1', name: '张老师', email: 'a@zuel.edu.cn', role: 'teacher' })
    const { container } = render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/workspace']}>
          <WorkspaceSidebar />
        </MemoryRouter>
      </QueryClientProvider>,
    )
    const aside = container.querySelector('.ws-sidebar')!
    expect(aside.className).toContain('collapsed')
    const expand = screen.getByRole('button', { name: '展开侧栏' }) as HTMLButtonElement
    expect(expand.getAttribute('aria-expanded')).toBe('false')

    fireEvent.click(expand)
    expect(aside.className).not.toContain('collapsed')
    const collapse = screen.getByRole('button', { name: '折叠侧栏' }) as HTMLButtonElement
    expect(collapse.getAttribute('aria-expanded')).toBe('true')

    fireEvent.click(collapse)
    expect(aside.className).toContain('collapsed')
  })
})

/** 渲染侧边栏，返回「管理后台」那条链接的 href；没有这条链接时返回 null。 */
function entryHref(user: Me): string | null {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Number.POSITIVE_INFINITY } },
  })
  queryClient.setQueryData(AUTH_QUERY_KEY, user)
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/workspace']}>
        <WorkspaceSidebar />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  const link = screen.queryByRole('link', { name: '管理后台' })
  return link ? link.getAttribute('href') : null
}
