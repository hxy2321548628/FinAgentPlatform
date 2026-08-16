import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { listFiles } from '../../api/files'
import { ArtifactStrip } from './ArtifactStrip'

afterEach(cleanup)

vi.mock('../../api/files', async importOriginal => {
  const original = await importOriginal<typeof import('../../api/files')>()
  return { ...original, listFiles: vi.fn() }
})

const listFilesMock = vi.mocked(listFiles)

function renderStrip(threadId: string, startedAt: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ArtifactStrip threadId={threadId} startedAt={startedAt} />
    </QueryClientProvider>,
  )
}

const TREE = {
  entries: [
    // 早于本轮 —— 不该出现
    { path: 'outputs/old.png', is_dir: false, size: 1000, modified_at: '2026-08-15T10:00:00Z' },
    // 本轮产物
    { path: 'outputs', is_dir: true, size: 0, modified_at: '2026-08-16T01:00:00Z' },
    { path: 'outputs/volatility_chart.png', is_dir: false, size: 86016, modified_at: '2026-08-16T01:02:00Z' },
    { path: 'outputs/rebalance_plan.csv', is_dir: false, size: 18432, modified_at: '2026-08-16T01:03:00Z' },
    // 非 outputs 目录 —— 不该出现
    { path: 'data/raw.csv', is_dir: false, size: 500, modified_at: '2026-08-16T01:04:00Z' },
  ],
  truncated: false,
}

beforeEach(() => {
  listFilesMock.mockReset()
})

describe('ArtifactStrip 归属过滤', () => {
  it('只显示本轮（modified_at ≥ started_at）的 outputs 文件', async () => {
    listFilesMock.mockResolvedValue(TREE)
    renderStrip('t1', '2026-08-16T00:00:00Z')
    expect(await screen.findByText('本轮产物（2）')).toBeTruthy()
    expect(screen.getByText('volatility_chart.png · 84.0 KB')).toBeTruthy()
    expect(screen.getByText('rebalance_plan.csv')).toBeTruthy()
    expect(screen.queryByText(/old\.png/)).toBeNull()
    expect(screen.queryByText(/raw\.csv/)).toBeNull()
  })

  it('PNG 渲染为缩略图，CSV 渲染为下载卡', async () => {
    listFilesMock.mockResolvedValue(TREE)
    renderStrip('t1', '2026-08-16T00:00:00Z')
    const img = await screen.findByRole('img') as HTMLImageElement
    expect(img.alt).toBe('volatility_chart.png')
    expect(img.src).toContain('/api/threads/t1/files/raw')
    expect(screen.getByRole('link', { name: '下载' }).getAttribute('href')).toContain('download=true')
  })

  it('没有本轮产物时不渲染任何内容', async () => {
    listFilesMock.mockResolvedValue({ entries: [TREE.entries[0]], truncated: false })
    const { container } = renderStrip('t1', '2026-08-16T00:00:00Z')
    // 等查询完成一拍
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(container.querySelector('.artifact-strip')).toBeNull()
  })

  it('文件树拉取失败时整体不渲染，不影响答复', async () => {
    listFilesMock.mockRejectedValue(new Error('网络错误'))
    const { container } = renderStrip('t1', '2026-08-16T00:00:00Z')
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(container.querySelector('.artifact-strip')).toBeNull()
  })

  it('超过 6 个产物默认折叠，可展开', async () => {
    const many = Array.from({ length: 8 }, (_, i) => ({
      path: `outputs/f${i}.csv`, is_dir: false, size: 100, modified_at: '2026-08-16T01:00:00Z',
    }))
    listFilesMock.mockResolvedValue({ entries: many, truncated: false })
    renderStrip('t1', '2026-08-16T00:00:00Z')
    const toggle = await screen.findByRole('button', { name: /展开其余 2 个/ })
    expect(screen.queryByText('f7.csv')).toBeNull()
    toggle.click()
    expect(await screen.findByText('f7.csv')).toBeTruthy()
  })
})
