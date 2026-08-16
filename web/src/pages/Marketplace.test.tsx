import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { PublicAgentListing } from '../api/types'
import { Marketplace } from './Marketplace'

const mocks = vi.hoisted(() => ({
  catalog: [] as PublicAgentListing[],
  listPublicCatalog: vi.fn(async () => mocks.catalog),
}))

vi.mock('../api/agents', async importOriginal => ({
  ...(await importOriginal<typeof import('../api/agents')>()),
  listPublicCatalog: mocks.listPublicCatalog,
}))

afterEach(() => {
  cleanup()
  mocks.catalog = []
  mocks.listPublicCatalog.mockReset()
  mocks.listPublicCatalog.mockImplementation(async () => mocks.catalog)
})

const AGENTS: PublicAgentListing[] = [
  {
    id: 'a1', owner_name: '张老师', name: '量化因子筛选器', description: '构建多因子模型',
    subject: '量化投资', call_count: 52, version: 2, updated_at: '2026-08-10T00:00:00Z',
  },
  {
    id: 'a2', owner_name: '陈老师', name: '企业财务异常检测', description: '稽核式比率检查',
    subject: '公司金融', call_count: 96, version: 1, updated_at: '2026-08-12T00:00:00Z',
  },
  {
    id: 's1', owner_name: '赵老师', name: '论文计量方法鉴别', description: '识别计量策略缺陷',
    subject: '学术科研', call_count: 64, version: 3,
    subagent_refs: [{ agent_id: 'a3', version: 1, name: '计量方法鉴别器' }],
    updated_at: '2026-08-14T00:00:00Z',
  },
]

/** 把当前 URL 暴露出来，验证筛选状态真的写进了 query。 */
function LocationProbe() {
  const location = useLocation()
  return <div data-testid="loc">{location.search}</div>
}

function show(initial = '/marketplace') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initial]}>
        <Marketplace />
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('Marketplace 真实目录', () => {
  it('默认落在协作场景 tab：只显示挂了子智能体的场景，统计来自真实数据', async () => {
    mocks.catalog = AGENTS
    show()
    expect(await screen.findByText('论文计量方法鉴别')).toBeTruthy()
    expect(screen.getByText('计量方法鉴别器')).toBeTruthy()
    expect(screen.queryByText('量化因子筛选器')).toBeNull()
    // 统计：212 次调用、1 个场景；教师数与学科数恰好都是 3
    expect(screen.getByText('212')).toBeTruthy()
    expect(screen.getByText('1')).toBeTruthy()
    expect(screen.getAllByText('3')).toHaveLength(2)
  })

  it('点「全部智能体」切 tab 并写 URL；学科筛选过滤并写 URL', async () => {
    mocks.catalog = AGENTS
    show()
    await screen.findByText('论文计量方法鉴别')
    fireEvent.click(screen.getByRole('button', { name: '全部智能体' }))
    expect(await screen.findByText('量化因子筛选器')).toBeTruthy()
    expect(screen.getByTestId('loc').textContent).toBe('?tab=agents')

    fireEvent.click(screen.getByRole('button', { name: '量化投资' }))
    expect(screen.getByText('量化因子筛选器')).toBeTruthy()
    expect(screen.queryByText('企业财务异常检测')).toBeNull()
    expect(screen.getByTestId('loc').textContent).toBe('?tab=agents&subject=%E9%87%8F%E5%8C%96%E6%8A%95%E8%B5%84')
  })

  it('从带参数的 URL 进入时直接落在对应 tab 与筛选', async () => {
    mocks.catalog = AGENTS
    show('/marketplace?tab=agents&subject=%E9%87%8F%E5%8C%96%E6%8A%95%E8%B5%84')
    expect(await screen.findByText('量化因子筛选器')).toBeTruthy()
    expect(screen.queryByText('企业财务异常检测')).toBeNull()
  })

  it('目录为空时给出去工作台发布的引导，不渲染残缺 UI', async () => {
    mocks.catalog = []
    show()
    expect(await screen.findByText(/还没有审核通过的场景/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '全部智能体' }))
    expect(await screen.findByText(/还没有审核通过的智能体/)).toBeTruthy()
  })

  it('目录拉取失败显示错误而不是假数据', async () => {
    mocks.listPublicCatalog.mockRejectedValueOnce(new Error('网络错误'))
    show()
    expect((await screen.findAllByRole('alert')).length).toBeGreaterThan(0)
    expect(screen.queryByText('212')).toBeNull()
  })
})
