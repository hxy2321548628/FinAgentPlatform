import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { SkillsLibrary } from './CapabilityLibraries'

const mocks = vi.hoisted(() => ({
  listCatalog: vi.fn(async () => [{
    id: 'skill-real', owner_id: 'owner-1', owner_name: '周老师', name: 'annualized-252',
    description: '统一按 252 个交易日年化', subject: '量化投资', visibility: 'private',
    call_count: 17, version: 3, file_count: 2, total_bytes: 2048, source: 'catalog', updated_at: '2026-08-14T00:00:00Z',
  }]),
}))

vi.mock('../../api/skills', async importOriginal => ({
  ...(await importOriginal<typeof import('../../api/skills')>()),
  listCatalog: mocks.listCatalog,
}))

afterEach(() => { cleanup(); mocks.listCatalog.mockClear() })

describe('SkillsLibrary', () => {
  it('只展示真实目录 API 返回的 Skill，不再渲染五条 mock', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(<QueryClientProvider client={client}><SkillsLibrary /></QueryClientProvider>)

    expect(await screen.findByText('annualized-252')).toBeTruthy()
    expect(screen.getByText('v3')).toBeTruthy()
    expect(screen.getByText(/2 个文件/)).toBeTruthy()
    expect(screen.queryByText('数据清洗')).toBeNull()
    expect(screen.queryByText('PDF 文本提取')).toBeNull()
    expect(screen.queryByText('财务指标计算')).toBeNull()
    expect(screen.queryByText('回归诊断')).toBeNull()
    expect(screen.queryByText('图表生成')).toBeNull()
  })
})
