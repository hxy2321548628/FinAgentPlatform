import { cleanup, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { threadKeys } from '../../api/threads'
import { Overview } from './Overview'

vi.mock('../../api/usage', () => ({
  usageKeys: { mine: () => ['usage', 'me'] },
  myUsage: vi.fn(async () => ({ available: false, tokens: 0, cost: 0, observations: 0 })),
}))

vi.mock('../../api/agents', () => ({
  agentKeys: { mine: () => ['agents', 'mine'] },
  listMine: vi.fn(async () => []),
}))

const listThreads = vi.fn()
vi.mock('../../api/threads', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../api/threads')>()
  return { ...actual, listThreads: (...args: unknown[]) => listThreads(...args) }
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

function show(client: QueryClient) {
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <Overview />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('Overview', () => {
  it('reads the thread list that the sidebar already cached', async () => {
    /**
     * **这一条挡的是一次真实的空白页。**
     *
     * `threadKeys.list()` 在 ThreadSidebar 与 MyData 里是 `useInfiniteQuery`，
     * 缓存形状是 `{pages:[…]}`；总览页若改用普通 `useQuery`，同一个键上就会存成
     * `{items:…}`。React Query 一个键只有一份缓存 —— 谁先加载谁的形状占住它，
     * 另一边读到的字段全是 `undefined`，页面一片空白且不报错。
     *
     * 单页渲染的测试抓不到这个：两个页面各自跑都是对的，只有共用一个
     * QueryClient 时才现形。所以这里**先按 infinite 的形状把缓存塞进去**，
     * 再渲染总览 —— 它必须读得出来。
     */
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    client.setQueryData(threadKeys.list(), {
      pages: [{
        items: [{
          id: 'thread-1',
          title: '波动率分析',
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        }],
        next_cursor: null,
      }],
      pageParams: [null],
    })

    show(client)

    // 读得出来就说明形状对上了。改回 useQuery 的话这里拿到的是 undefined，
    // 页面停在「还没有会话」——正是用户报的那个空白
    expect(await screen.findByText('波动率分析')).toBeTruthy()
  })

  it('展示分析流程与常用资源，避免总览页内容过空', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    listThreads.mockResolvedValue({ items: [], next_cursor: null })

    show(client)

    expect(await screen.findByText('从问题到分析成果')).toBeTruthy()
    expect(screen.getByText('常用资源')).toBeTruthy()
  })

  it('says the ledger is missing instead of showing a zero', async () => {
    /** 「没接账本」与「这个月没用过」都显示 0 的话，教师无从判断是哪一种。 */
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    listThreads.mockResolvedValue({ items: [], next_cursor: null })

    show(client)

    expect(await screen.findByText('用量账本未接入')).toBeTruthy()
  })
})
