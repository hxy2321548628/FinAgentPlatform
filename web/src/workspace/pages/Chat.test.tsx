import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { RunHistory } from '../../api/types'

const mocks = vi.hoisted(() => ({
  runs: [] as RunHistory[],
  loadedRuns: new Set<string>(),
  connectionError: null as unknown,
  connectionRetryable: false,
  useRunEvents: vi.fn(),
}))

vi.mock('react-router-dom', () => ({
  useParams: () => ({ threadId: 'thread-1' }),
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
  useMutation: () => ({
    isError: false,
    isPending: false,
    mutate: vi.fn(),
    mutateAsync: vi.fn(),
  }),
}))

vi.mock('../../hooks/useRunEvents', () => ({
  useRunEvents: (...args: unknown[]) => mocks.useRunEvents(...args),
}))

vi.mock('../components/ThreadSidebar', () => ({ ThreadSidebar: () => null }))
vi.mock('../components/MessageList', () => ({ MessageList: () => null }))
vi.mock('../components/ChatInput', () => ({ ChatInput: () => null }))
vi.mock('../components/WorkspaceFiles', () => ({ WorkspaceFiles: () => null }))

import { Chat } from './Chat'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
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

describe('Chat event replay selection', () => {
  beforeEach(() => {
    mocks.runs = []
    mocks.loadedRuns.clear()
    mocks.connectionError = null
    mocks.connectionRetryable = false
    mocks.useRunEvents.mockReset()
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

  it('automatically replays the newest terminal run and leaves older terminal runs on demand', () => {
    // The history endpoint is newest-first; Chat renders it oldest-first.
    mocks.runs = [run('newest', 'succeeded'), run('older', 'succeeded')]

    render(<Chat />)

    expect(enabledFor('newest')).toBe(true)
    expect(enabledFor('older')).toBe(false)
    const replay = screen.getByRole('button', { name: '查看本轮回答与过程' })

    fireEvent.click(replay)

    expect(enabledFor('older')).toBe(true)
  })

  it('prioritizes the live run for the sole automatic subscription', () => {
    mocks.runs = [run('newest-terminal', 'succeeded'), run('live', 'running'), run('older', 'succeeded')]

    render(<Chat />)

    expect(enabledFor('live')).toBe(true)
    expect(enabledFor('newest-terminal')).toBe(false)
    expect(enabledFor('older')).toBe(false)
  })

  it('does not offer to load a historical run whose events are already rendered', () => {
    mocks.runs = [run('newest', 'succeeded'), run('older', 'succeeded')]
    mocks.loadedRuns.add('older')

    render(<Chat />)

    expect(screen.queryByRole('button', { name: '查看本轮回答与过程' })).toBeNull()
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
