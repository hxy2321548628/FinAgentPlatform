import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { ToastProvider } from '../../components/ui/Toast'
import { ThreadSidebar } from './ThreadSidebar'

const mocks = vi.hoisted(() => ({
  updateThread: vi.fn(),
  listThreads: vi.fn(),
  deleteThread: vi.fn(),
}))

vi.mock('../../api/threads', async importOriginal => {
  const original = await importOriginal<typeof import('../../api/threads')>()
  return {
    ...original,
    listThreads: mocks.listThreads,
    deleteThread: mocks.deleteThread,
    updateThread: mocks.updateThread,
  }
})

beforeEach(() => {
  mocks.listThreads.mockResolvedValue({
    items: [{ id: 't1', title: '波动率分析', created_at: '2026-08-15T00:00:00Z', updated_at: '2026-08-16T00:00:00Z' }],
    next_cursor: null,
  })
  mocks.updateThread.mockResolvedValue({ id: 't1' })
  mocks.deleteThread.mockResolvedValue(undefined)
})

afterEach(() => {
  cleanup()
  mocks.updateThread.mockReset()
  mocks.listThreads.mockReset()
  mocks.deleteThread.mockReset()
})

function show(initial = '/workspace/chat/t1') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <MemoryRouter initialEntries={[initial]}>
          <Routes>
            <Route path="/workspace/chat" element={<><ThreadSidebar /><div data-testid="welcome-route" /></>} />
            <Route path="/workspace/chat/:threadId" element={<><ThreadSidebar /><div data-testid="thread-route" /></>} />
          </Routes>
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  )
}

async function openRowMenu() {
  await screen.findByText('波动率分析')
  fireEvent.keyDown(screen.getByRole('button', { name: '会话操作：波动率分析' }), { key: 'ArrowDown' })
}

describe('ThreadSidebar 三点菜单', () => {
  it('点重命名出现输入框，Enter 提交 updateThread', async () => {
    show()
    await openRowMenu()
    fireEvent.click(await screen.findByText('重命名'))
    const input = screen.getByRole('textbox', { name: '会话名称' }) as HTMLInputElement
    expect(input.value).toBe('波动率分析')
    fireEvent.change(input, { target: { value: '持仓波动率复盘' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    // React Query 的 mutate 异步执行 mutationFn，断言等一拍
    await waitFor(() => expect(mocks.updateThread).toHaveBeenCalledWith('t1', { title: '持仓波动率复盘' }))
  })

  it('Esc 取消重命名，不发请求', async () => {
    show()
    await openRowMenu()
    fireEvent.click(await screen.findByText('重命名'))
    const input = screen.getByRole('textbox', { name: '会话名称' })
    fireEvent.change(input, { target: { value: '不该提交' } })
    fireEvent.keyDown(input, { key: 'Escape' })
    expect(mocks.updateThread).not.toHaveBeenCalled()
    expect(screen.queryByRole('textbox', { name: '会话名称' })).toBeNull()
  })

  it('清空后提交不请求，恢复原标题', async () => {
    show()
    await openRowMenu()
    fireEvent.click(await screen.findByText('重命名'))
    const input = screen.getByRole('textbox', { name: '会话名称' })
    fireEvent.change(input, { target: { value: '   ' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(mocks.updateThread).not.toHaveBeenCalled()
    expect(screen.getByText('波动率分析')).toBeTruthy()
  })

  it('点删除经确认弹窗后调用 deleteThread', async () => {
    show()
    await openRowMenu()
    fireEvent.click(await screen.findByText('删除'))
    const dialog = await screen.findByRole('alertdialog')
    fireEvent.click(within(dialog).getByRole('button', { name: '删除' }))

    await waitFor(() => expect(mocks.deleteThread).toHaveBeenCalledWith('t1', expect.anything()))
  })

  it('删除确认可取消', async () => {
    show()
    await openRowMenu()
    fireEvent.click(await screen.findByText('删除'))
    const dialog = await screen.findByRole('alertdialog')
    fireEvent.click(within(dialog).getByRole('button', { name: '取消' }))

    expect(mocks.deleteThread).not.toHaveBeenCalled()
  })
})

describe('ThreadSidebar 新建与搜索', () => {
  it('新建分析只是导航到无会话欢迎页，不建会话（幂等）', async () => {
    show()
    await screen.findByText('波动率分析')
    fireEvent.click(screen.getByRole('button', { name: '＋ 新建分析' }))

    await waitFor(() => expect(screen.getByTestId('welcome-route')).toBeTruthy())
  })

  it('搜索会话：输入停顿后把关键词交给接口', async () => {
    show()
    await screen.findByText('波动率分析')
    fireEvent.change(screen.getByRole('searchbox', { name: '搜索会话' }), { target: { value: '波动' } })

    await waitFor(() => expect(mocks.listThreads).toHaveBeenCalledWith(null, 20, '波动'))
  })

  it('搜索无结果时给空态提示', async () => {
    mocks.listThreads.mockResolvedValue({ items: [], next_cursor: null })
    show()
    await screen.findByText('还没有分析对话')
    fireEvent.change(screen.getByRole('searchbox', { name: '搜索会话' }), { target: { value: '波动' } })

    await screen.findByText('没有匹配“波动”的会话')
  })
})

describe('ThreadSidebar 进行中状态', () => {
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
