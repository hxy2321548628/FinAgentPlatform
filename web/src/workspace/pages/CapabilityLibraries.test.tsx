import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { ApiError } from '../../api/request'
import type { McpServer } from '../../api/types'
import { McpLibrary, SkillsLibrary } from './CapabilityLibraries'

const mocks = vi.hoisted(() => ({
  listCatalog: vi.fn(async () => [{
    id: 'skill-real', owner_id: 'owner-1', owner_name: '周老师', name: 'annualized-252',
    description: '统一按 252 个交易日年化', subject: '量化投资', visibility: 'private',
    call_count: 17, version: 3, file_count: 2, total_bytes: 2048, source: 'catalog', updated_at: '2026-08-14T00:00:00Z',
  }]),
  listVersionFiles: vi.fn(async () => [
    { path: 'SKILL.md', size: 32 },
    { path: 'scripts/report.py', size: 22 },
  ]),
  readVersionFile: vi.fn(async (_skillId: string, _version: number, path: string) => ({
    path, size: 22, is_binary: false, content: path === 'SKILL.md' ? '# 年化规则\n默认按 252 日。' : 'print("252 个交易日")',
  })),
  listMcpCatalog: vi.fn(async (): Promise<McpServer[]> => [{
    id: 'mcp-real', name: '论文检索', description: '按关键词检索论文', url: 'https://mcp.example.edu/mcp',
    transport: 'streamable_http', has_credential: false, tool_names: ['search_paper'], latency_note: '1 秒',
    stores_user_data: false, sends_data_out: true, has_write_operation: false, status: 'enabled', disabled_reason: null,
    created_at: '2026-08-14T00:00:00Z', updated_at: '2026-08-14T00:00:00Z',
  }]),
}))

vi.mock('../../api/skills', async importOriginal => ({
  ...(await importOriginal<typeof import('../../api/skills')>()),
  listCatalog: mocks.listCatalog,
  listVersionFiles: mocks.listVersionFiles,
  readVersionFile: mocks.readVersionFile,
}))

vi.mock('../../api/mcp', async importOriginal => ({
  ...(await importOriginal<typeof import('../../api/mcp')>()),
  listCatalog: mocks.listMcpCatalog,
}))

afterEach(() => { cleanup(); sessionStorage.clear(); vi.clearAllMocks() })

describe('SkillsLibrary', () => {
  it('只展示真实目录 API 返回的 Skill，不再渲染五条 mock', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(<MemoryRouter><QueryClientProvider client={client}><SkillsLibrary /></QueryClientProvider></MemoryRouter>)

    expect(await screen.findByText('annualized-252')).toBeTruthy()
    expect(screen.getByText('v3')).toBeTruthy()
    expect(screen.getByText(/2 个文件/)).toBeTruthy()
    expect(screen.queryByText('数据清洗')).toBeNull()
    expect(screen.queryByText('PDF 文本提取')).toBeNull()
    expect(screen.queryByText('财务指标计算')).toBeNull()
    expect(screen.queryByText('回归诊断')).toBeNull()
    expect(screen.queryByText('图表生成')).toBeNull()
  })

  it('可直接使用 Skill 开始新分析', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(<MemoryRouter><QueryClientProvider client={client}><SkillsLibrary /></QueryClientProvider></MemoryRouter>)

    fireEvent.click(await screen.findByRole('button', { name: '使用 Skill' }))

    expect(JSON.parse(sessionStorage.getItem('zuel.picked-agent-config') ?? 'null')).toEqual({ skills: ['skill-real'] })
  })

  it('文件浏览路由未加载时给出明确提示', async () => {
    mocks.listVersionFiles.mockRejectedValueOnce(new ApiError(404, 'NOT_FOUND', 'Not Found'))
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(<MemoryRouter><QueryClientProvider client={client}><SkillsLibrary /></QueryClientProvider></MemoryRouter>)

    fireEvent.click(await screen.findByRole('button', { name: '查看详情' }))

    expect(await screen.findByText('文件浏览服务尚未加载，请刷新页面后重试')).toBeTruthy()
  })

  it('详情以文件树浏览发布版本内容，文件只读展示', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(<MemoryRouter><QueryClientProvider client={client}><SkillsLibrary /></QueryClientProvider></MemoryRouter>)

    fireEvent.click(await screen.findByRole('button', { name: '查看详情' }))

    expect(await screen.findByText(/年化规则/)).toBeTruthy()
    expect(screen.getByRole('button', { name: 'scripts' })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'report.py' }))
    await screen.findByText('Python')
    expect(mocks.readVersionFile).toHaveBeenLastCalledWith('skill-real', 3, 'scripts/report.py')
    expect(screen.getByLabelText('只读代码查看器')).toBeTruthy()
    expect(document.querySelector('.workspace-code-surface[data-language="python"]')).toBeTruthy()
    expect(document.querySelector('.workspace-code-gutter')).toBeTruthy()
    await waitFor(() => expect(document.querySelector('.workspace-code-highlighted .shiki')).toBeTruthy())
    expect(screen.queryByRole('textbox')).toBeNull()
  })

})

describe('McpLibrary', () => {
  it('与后台共用同一套 MCP 能力抽屉', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(<MemoryRouter><QueryClientProvider client={client}><McpLibrary /></QueryClientProvider></MemoryRouter>)

    fireEvent.click(await screen.findByRole('button', { name: '查看 MCP 能力' }))

    const detail = screen.getByRole('dialog')
    expect(detail.classList.contains('dialog-drawer')).toBe(true)
    expect(within(detail).getByText('https://mcp.example.edu/mcp')).toBeTruthy()
    expect(within(detail).getByText('search_paper')).toBeTruthy()
    expect(within(detail).getByText('声明会转发给第三方')).toBeTruthy()
  })
})
