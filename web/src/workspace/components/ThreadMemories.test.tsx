import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { MemorySummary } from '../../api/types'
import { ToastProvider } from '../../components/ui/Toast'
import { ThreadMemories } from './ThreadMemories'

const mocks = vi.hoisted(() => ({
  listMemories: vi.fn(),
  getMemory: vi.fn(),
  deleteMemory: vi.fn(),
}))

vi.mock('../../api/memories', async importOriginal => ({
  ...(await importOriginal<typeof import('../../api/memories')>()),
  listMemories: mocks.listMemories,
  getMemory: mocks.getMemory,
  deleteMemory: mocks.deleteMemory,
}))

let memories: MemorySummary[]

beforeEach(() => {
  memories = [{
    slug: 'risk-profile',
    name: '风险偏好',
    description: '教师偏好低波动、重视回撤控制',
    type: 'user',
    updated_at: '2026-08-20T08:30:00Z',
  }]
  mocks.listMemories.mockImplementation(async () => ({ items: memories }))
  mocks.getMemory.mockResolvedValue({ ...memories[0], content: '偏好低波动，并控制最大回撤。' })
  mocks.deleteMemory.mockImplementation(async () => { memories = [] })
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider><ThreadMemories threadId="thread-1" /></ToastProvider>
    </QueryClientProvider>,
  )
}

describe('ThreadMemories', () => {
  it('列表显示名称、描述、类型和更新时间，点击后读取正文详情', async () => {
    show()

    expect(await screen.findByText('风险偏好')).toBeTruthy()
    expect(screen.getByText('教师偏好低波动、重视回撤控制')).toBeTruthy()
    expect(screen.getByText('用户偏好')).toBeTruthy()
    expect(screen.getByText(/2026/)).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: '查看记忆：风险偏好' }))

    expect(await screen.findByText('偏好低波动，并控制最大回撤。')).toBeTruthy()
    expect(mocks.getMemory).toHaveBeenCalledWith('thread-1', 'risk-profile')
  })

  it('删除必须二次确认，取消保留详情，确认后列表和详情都消失', async () => {
    show()
    fireEvent.click(await screen.findByRole('button', { name: '查看记忆：风险偏好' }))
    expect(await screen.findByText('偏好低波动，并控制最大回撤。')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: '删除记忆' }))
    let dialog = await screen.findByRole('alertdialog')
    fireEvent.click(within(dialog).getByRole('button', { name: '取消' }))
    expect(mocks.deleteMemory).not.toHaveBeenCalled()
    expect(screen.getByText('偏好低波动，并控制最大回撤。')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: '删除记忆' }))
    dialog = await screen.findByRole('alertdialog')
    fireEvent.click(within(dialog).getByRole('button', { name: '删除' }))

    await waitFor(() => expect(mocks.deleteMemory).toHaveBeenCalledWith('thread-1', 'risk-profile'))
    await waitFor(() => expect(screen.queryByText('风险偏好')).toBeNull())
    expect(screen.queryByText('偏好低波动，并控制最大回撤。')).toBeNull()
    expect(await screen.findByText('这个会话还没有可管理的记忆。')).toBeTruthy()
  })

  it('空列表与请求失败都有明确中文状态', async () => {
    memories = []
    show()
    expect(await screen.findByText('这个会话还没有可管理的记忆。')).toBeTruthy()

    cleanup()
    mocks.listMemories.mockRejectedValue(new Error('服务暂时不可用'))
    show()

    expect((await screen.findByRole('alert')).textContent).toBe('记忆加载失败：服务暂时不可用')
  })
})
