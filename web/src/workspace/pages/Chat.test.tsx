import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { RunHistory } from '../../api/types'

const mocks = vi.hoisted(() => ({
  runs: [] as RunHistory[],
  loadedRuns: new Set<string>(),
  connectionError: null as unknown,
  connectionRetryable: false,
  useRunEvents: vi.fn(),
  createThread: vi.fn(),
  submitRun: vi.fn(),
  navigate: vi.fn(),
  chatInputProps: null as null | Record<string, unknown>,
}))

const routeState: { threadId?: string } = { threadId: 'thread-1' }

vi.mock('react-router-dom', () => ({
  useParams: () => ({ threadId: routeState.threadId }),
  useNavigate: () => mocks.navigate,
}))

vi.mock('../../api/threads', () => ({
  createThread: (...args: unknown[]) => mocks.createThread(...args),
  getThread: vi.fn(),
  updateThread: vi.fn(),
  threadKeys: {
    all: ['threads'],
    list: () => ['threads', 'list'],
    detail: (id: string) => ['threads', 'detail', id],
  },
}))

vi.mock('../../api/runs', () => ({
  approveRun: vi.fn(),
  cancelRun: vi.fn(),
  getRun: vi.fn(),
  listRuns: vi.fn(),
  submitRun: (...args: unknown[]) => mocks.submitRun(...args),
  runKeys: {
    all: ['runs'],
    list: (id: string) => ['runs', 'list', id],
  },
}))

vi.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
  useQuery: () => ({
    data: { id: 'thread-1', title: '测试会话', agent_config: {} },
    isError: false,
  }),
  useInfiniteQuery: () => ({
    data: { pages: [{ items: mocks.runs, next_cursor: null }] },
    isPending: false,
    isError: false,
    hasNextPage: false,
    isFetchingNextPage: false,
    fetchNextPage: vi.fn(),
  }),
  useMutation: (options: { mutationFn?: (...args: never[]) => unknown }) => ({
    isError: false,
    isPending: false,
    mutate: vi.fn(),
    mutateAsync: options.mutationFn ?? vi.fn(),
  }),
}))

vi.mock('../../hooks/useRunEvents', () => ({
  useRunEvents: (...args: unknown[]) => mocks.useRunEvents(...args),
}))

vi.mock('../components/ThreadSidebar', () => ({ ThreadSidebar: () => null }))
vi.mock('../components/MessageList', () => ({ MessageList: () => null }))
vi.mock('../components/ChatInput', () => ({
  ChatInput: (props: Record<string, unknown>) => {
    mocks.chatInputProps = props
    return null
  },
}))
vi.mock('../components/WorkspaceFiles', () => ({ WorkspaceFiles: () => null }))

import { Chat } from './Chat'

/** 可控的 IntersectionObserver：jsdom 不提供，触发时机由测试决定。 */
class FakeIntersectionObserver {
  static instances: FakeIntersectionObserver[] = []
  callback: IntersectionObserverCallback
  observed: Element[] = []
  constructor(callback: IntersectionObserverCallback) {
    this.callback = callback
    FakeIntersectionObserver.instances.push(this)
  }
  observe(node: Element) {
    this.observed.push(node)
  }
  unobserve() {}
  disconnect() {}
  trigger(isIntersecting: boolean) {
    this.callback([{ isIntersecting } as IntersectionObserverEntry], this as unknown as IntersectionObserver)
  }
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  mocks.chatInputProps = null
})

beforeEach(() => {
  routeState.threadId = 'thread-1'
  mocks.runs = []
  mocks.loadedRuns.clear()
  mocks.connectionError = null
  mocks.connectionRetryable = false
  mocks.useRunEvents.mockReset()
  mocks.createThread.mockReset()
  mocks.submitRun.mockReset()
  mocks.navigate.mockReset()
  FakeIntersectionObserver.instances = []
  vi.stubGlobal('IntersectionObserver', FakeIntersectionObserver)
  mocks.useRunEvents.mockImplementation((runId: string, status: RunHistory['status']) => ({
    status,
    items: mocks.loadedRuns.has(runId) ? [{ kind: 'answer', path: [], text: '已回放' }] : [],
    pendingActions: null,
    connectionAvailable: true,
    connectionError: mocks.connectionError,
    connectionRetryable: mocks.connectionRetryable,
    markApprovalSubmitted: vi.fn(),
  }))
})

function run(id: string, status: RunHistory['status']): RunHistory {
  return {
    id,
    status,
    content: `问题 ${id}`,
    agent_config: {},
    error_code: null,
    error_message: null,
    started_at: '2026-08-14T00:00:00Z',
    ended_at: status === 'running' ? null : '2026-08-14T00:01:00Z',
  }
}

function enabledFor(runId: string): boolean | undefined {
  const call = mocks.useRunEvents.mock.calls.findLast(args => args[0] === runId)
  return call?.[2]?.enabled as boolean | undefined
}

function observerFor(runId: string): FakeIntersectionObserver | undefined {
  return FakeIntersectionObserver.instances.find(one =>
    one.observed.some(node => node.getAttribute('data-run-id') === runId))
}

describe('Chat 历史轮次视口自动回放', () => {
  it('滚进视口的终态轮次自动回放，不再需要逐条点击', () => {
    mocks.runs = [run('newest', 'succeeded'), run('older', 'succeeded')]

    render(<Chat />)

    expect(enabledFor('newest')).toBe(false)
    expect(enabledFor('older')).toBe(false)
    // 浏览器里页面滚动到最新一轮时 IO 自动触发；测试里手动触发
    act(() => { observerFor('newest')?.trigger(true) })
    expect(enabledFor('newest')).toBe(true)
    expect(enabledFor('older')).toBe(false)
    act(() => { observerFor('older')?.trigger(true) })
    expect(enabledFor('older')).toBe(true)
  })

  it('回放粘住不回退：离开视口后仍保持回放', () => {
    mocks.runs = [run('newest', 'succeeded')]

    render(<Chat />)
    const observer = observerFor('newest')
    act(() => { observer?.trigger(true) })
    act(() => { observer?.trigger(false) })

    expect(enabledFor('newest')).toBe(true)
  })

  it('运行中的轮次无需视口即回放', () => {
    mocks.runs = [run('newest-terminal', 'succeeded'), run('live', 'running')]

    render(<Chat />)

    expect(enabledFor('live')).toBe(true)
    expect(enabledFor('newest-terminal')).toBe(false)
  })

  it('保留「查看本轮回答与过程」作为事件流异常的兜底入口', () => {
    mocks.runs = [run('newest', 'succeeded')]

    render(<Chat />)

    const replay = screen.getByRole('button', { name: '查看本轮回答与过程' })
    expect(enabledFor('newest')).toBe(false)
    fireEvent.click(replay)
    expect(enabledFor('newest')).toBe(true)
  })

  it('distinguishes a fatal event stream error from a retryable disconnect', () => {
    mocks.runs = [run('newest', 'running')]
    mocks.connectionError = { retryable: false }

    const view = render(<Chat />)
    expect(screen.getByRole('alert').textContent).toBe('事件流连接失败，请刷新页面后重试。')

    mocks.connectionRetryable = true
    view.rerender(<Chat />)
    expect(screen.getByRole('alert').textContent).toBe('事件流连接中断，正在等待传输层重连。')
  })

  it('starts at the latest content and only follows updates while the user remains at the bottom', () => {
    vi.spyOn(HTMLElement.prototype, 'scrollHeight', 'get').mockReturnValue(1000)
    vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(200)
    mocks.runs = [run('newest', 'running')]

    const { rerender } = render(<Chat />)
    const region = screen.getByTestId('chat-scroll-region')

    expect(region.scrollTop).toBe(1000)

    region.scrollTop = 350
    fireEvent.scroll(region)
    mocks.loadedRuns.add('newest')
    rerender(<Chat />)

    expect(region.scrollTop).toBe(350)

    region.scrollTop = 800
    fireEvent.scroll(region)
    rerender(<Chat />)

    expect(region.scrollTop).toBe(1000)
  })
})

describe('Chat 欢迎页与懒创建', () => {
  it('没有会话时显示居中欢迎页，输入区可用', () => {
    routeState.threadId = undefined

    render(<Chat />)

    expect(screen.getByText('开始一次新的分析')).toBeTruthy()
    expect(screen.queryByTestId('chat-scroll-region')).toBeTruthy()
    expect(mocks.chatInputProps?.disabled).toBe(false)
    expect(mocks.createThread).not.toHaveBeenCalled()
  })

  it('第一次发送才创建会话：先建会话、提交成功后再跳转', async () => {
    routeState.threadId = undefined
    mocks.createThread.mockResolvedValue({ id: 'thread-new' })
    mocks.submitRun.mockResolvedValue({ id: 'run-1' })

    render(<Chat />)
    const onSend = mocks.chatInputProps?.onSend as (text: string, config: unknown) => Promise<void>
    await onSend('算个波动率', undefined)

    await waitFor(() => expect(mocks.submitRun).toHaveBeenCalledWith('thread-new', '算个波动率', undefined))
    expect(mocks.navigate).toHaveBeenCalledWith('/workspace/chat/thread-new', { replace: true })
  })

  it('提交失败时不跳转、不丢会话（草稿保留在欢迎页）', async () => {
    routeState.threadId = undefined
    mocks.createThread.mockResolvedValue({ id: 'thread-new' })
    mocks.submitRun.mockRejectedValue(new Error('配额不足'))

    render(<Chat />)
    const onSend = mocks.chatInputProps?.onSend as (text: string, config: unknown) => Promise<void>
    await expect(onSend('算个波动率', undefined)).rejects.toThrow('配额不足')

    expect(mocks.navigate).not.toHaveBeenCalled()
    expect(screen.getByText('开始一次新的分析')).toBeTruthy()
  })
})
