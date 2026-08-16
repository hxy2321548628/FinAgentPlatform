import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { ToastProvider } from '../../components/ui/Toast'
import { ThreadSidebar } from './ThreadSidebar'

const mocks = vi.hoisted(() => ({
  updateThread: vi.fn(),
  listThreads: vi.fn(),
}))

vi.mock('../../api/threads', async importOriginal => {
  const original = await importOriginal<typeof import('../../api/threads')>()
  return {
    ...original,
    listThreads: mocks.listThreads,
    createThread: vi.fn(),
    deleteThread: vi.fn(),
    updateThread: mocks.updateThread,
  }
})

beforeEach(() => {
  mocks.listThreads.mockResolvedValue({
    items: [{ id: 't1', title: '波动率分析', created_at: '2026-08-15T00:00:00Z', updated_at: '2026-08-16T00:00:00Z' }],
    next_cursor: null,
  })
  mocks.updateThread.mockResolvedValue({ id: 't1' })
})

afterEach(() => {
  cleanup()
  mocks.updateThread.mockReset()
  mocks.listThreads.mockReset()
})

function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <MemoryRouter initialEntries={['/workspace/chat/t1']}>
          <Routes>
            <Route path="/workspace/chat/:threadId" element={<ThreadSidebar />} />
          </Routes>
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  )
}

describe('ThreadSidebar 行内重命名', () => {
  it('点重命名出现输入框，Enter 提交 updateThread', async () => {
    show()
    await screen.findByText('波动率分析')
    fireEvent.click(screen.getByRole('button', { name: '重命名波动率分析' }))
    const input = screen.getByRole('textbox', { name: '会话名称' }) as HTMLInputElement
    expect(input.value).toBe('波动率分析')
    fireEvent.change(input, { target: { value: '持仓波动率复盘' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    // React Query 的 mutate 异步执行 mutationFn，断言等一拍
    await waitFor(() => expect(mocks.updateThread).toHaveBeenCalledWith('t1', { title: '持仓波动率复盘' }))
  })

  it('Esc 取消重命名，不发请求', async () => {
    show()
    await screen.findByText('波动率分析')
    fireEvent.click(screen.getByRole('button', { name: '重命名波动率分析' }))
    const input = screen.getByRole('textbox', { name: '会话名称' })
    fireEvent.change(input, { target: { value: '不该提交' } })
    fireEvent.keyDown(input, { key: 'Escape' })
    expect(mocks.updateThread).not.toHaveBeenCalled()
    expect(screen.queryByRole('textbox', { name: '会话名称' })).toBeNull()
  })

  it('清空后提交不请求，恢复原标题', async () => {
    show()
    await screen.findByText('波动率分析')
    fireEvent.click(screen.getByRole('button', { name: '重命名波动率分析' }))
    const input = screen.getByRole('textbox', { name: '会话名称' })
    fireEvent.change(input, { target: { value: '   ' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(mocks.updateThread).not.toHaveBeenCalled()
    expect(screen.getByText('波动率分析')).toBeTruthy()
  })

  it('还在跑的会话显示进行中状态点与状态文案', async () => {
    mocks.listThreads.mockResolvedValue({
      items: [{
        id: 't1', title: '波动率分析',
        created_at: '2026-08-15T00:00:00Z', updated_at: '2026-08-16T00:00:00Z',
        live_run_status: 'running',
      }],
      next_cursor: null,
    })
    show()
    await screen.findByText('波动率分析')
    expect(screen.getByText('分析中')).toBeTruthy()
    expect(document.querySelector('.thread-live-dot')).toBeTruthy()
  })

  it('没有进行中 run 的会话不显示状态点', async () => {
    show()
    await screen.findByText('波动率分析')
    expect(screen.queryByText('分析中')).toBeNull()
    expect(document.querySelector('.thread-live-dot')).toBeNull()
  })
})
