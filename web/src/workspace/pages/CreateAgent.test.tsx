import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { CreateAgent } from './CreateAgent'

const mocks = vi.hoisted(() => ({
  createAgent: vi.fn(async () => ({})),
  listAvailable: vi.fn(async () => [{
    id: 'skill-1', owner_id: 'owner-1', owner_name: '李老师', name: 'annualized-252',
    description: '按 252 个交易日年化', subject: '量化投资', visibility: 'private',
    call_count: 3, version: 2, file_count: 1, total_bytes: 120, source: 'catalog', updated_at: '2026-08-14T00:00:00Z',
  }]),
  listSubagentCandidates: vi.fn(async () => [{
    id: 'agent-child', owner_id: 'owner-2', owner_name: '王老师', name: '波动率专家',
    description: '计算波动率', subject: '量化投资', visibility: 'group', call_count: 2, version: 1,
    system_prompt: '只计算波动率', source: 'group', updated_at: '2026-08-15T00:00:00Z',
  }]),
  listMcpCatalog: vi.fn(async () => [{
    id: 'mcp-1', name: '论文检索', description: '检索金融学论文', url: 'https://mcp.example.com',
    transport: 'streamable_http' as const, has_credential: false, tool_names: ['search_paper'], latency_note: '',
    stores_user_data: false, sends_data_out: false, has_write_operation: false, status: 'enabled' as const,
    disabled_reason: null, created_at: '2026-08-15T00:00:00Z', updated_at: '2026-08-15T00:00:00Z',
  }]),
}))

vi.mock('../../api/agents', async importOriginal => ({
  ...(await importOriginal<typeof import('../../api/agents')>()),
  createAgent: mocks.createAgent,
  listSubagentCandidates: mocks.listSubagentCandidates,
}))
vi.mock('../../api/skills', async importOriginal => ({
  ...(await importOriginal<typeof import('../../api/skills')>()),
  listAvailable: mocks.listAvailable,
}))
vi.mock('../../api/mcp', async importOriginal => ({
  ...(await importOriginal<typeof import('../../api/mcp')>()),
  listCatalog: mocks.listMcpCatalog,
}))

afterEach(() => {
  cleanup()
  mocks.createAgent.mockClear()
  mocks.listAvailable.mockClear()
  mocks.listSubagentCandidates.mockClear()
  mocks.listMcpCatalog.mockClear()
})

function mount(path = '/workspace/my-agents/create') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/workspace/my-agents/create" element={<CreateAgent />} />
          <Route path="/workspace/my-scenarios/create" element={<CreateAgent />} />
          <Route path="/workspace/my-agents" element={<div>我的智能体</div>} />
          <Route path="/workspace/my-scenarios" element={<div>我的场景</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('CreateAgent', () => {
  it('智能体只配置基本信息与系统提示词', async () => {
    mount()
    expect(screen.getByRole('navigation', { name: '智能体配置步骤' })).toBeTruthy()
    expect(screen.getByText('第 1 / 2 步 · 基本信息')).toBeTruthy()
    expect(screen.queryByRole('button', { name: /能力组件/ })).toBeNull()
    expect(screen.queryByRole('button', { name: /协作编排/ })).toBeNull()
    expect(mocks.listAvailable).not.toHaveBeenCalled()
    expect(mocks.listSubagentCandidates).not.toHaveBeenCalled()
    expect(mocks.listMcpCatalog).not.toHaveBeenCalled()

    fireEvent.change(screen.getByPlaceholderText('如：企业财务异常检测'), { target: { value: '收益率助手' } })
    fireEvent.click(screen.getByRole('button', { name: /下一步/ }))
    fireEvent.change(screen.getByPlaceholderText(/严谨的金融分析师/), { target: { value: '请按统一口径计算收益率' } })
    expect(screen.getByText('第 2 / 2 步 · 行为设定')).toBeTruthy()
    expect(screen.queryByRole('button', { name: /下一步/ })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: /创建草稿/ }))

    await waitFor(() => expect(mocks.createAgent).toHaveBeenCalledWith(expect.objectContaining({
      skills: [],
      mcps: [],
      subagents: [],
    })))
  })

  it('场景保留系统提示词、Skill、MCP 与子智能体配置', async () => {
    mount('/workspace/my-scenarios/create')
    expect(screen.getByText('第 1 / 4 步 · 基本信息')).toBeTruthy()
    expect(screen.getByRole('button', { name: /能力组件/ })).toBeTruthy()
    expect(screen.getByRole('button', { name: /协作编排/ })).toBeTruthy()

    fireEvent.change(screen.getByPlaceholderText('如：企业信用风险联合研判'), { target: { value: '信用风险场景' } })
    fireEvent.click(screen.getByRole('button', { name: /行为设定/ }))
    fireEvent.change(screen.getByPlaceholderText(/严谨的金融分析师/), { target: { value: '综合多个智能体完成信用风险研判' } })
    fireEvent.click(screen.getByRole('button', { name: /能力组件/ }))
    fireEvent.click(await screen.findByRole('checkbox', { name: /annualized-252/ }))
    fireEvent.click(screen.getByRole('tab', { name: /MCP/ }))
    fireEvent.click(await screen.findByRole('checkbox', { name: '论文检索' }))
    fireEvent.click(screen.getByRole('button', { name: /协作编排/ }))
    fireEvent.click(await screen.findByRole('checkbox', { name: /波动率专家/ }))
    fireEvent.click(screen.getByRole('button', { name: /创建草稿/ }))

    await waitFor(() => expect(mocks.createAgent).toHaveBeenCalledWith(expect.objectContaining({
      skills: ['skill-1'],
      mcps: ['mcp-1'],
      subagents: ['agent-child'],
    })))
  })

  it('场景编辑器明确要求选择子智能体', async () => {
    mount('/workspace/my-scenarios/create')
    expect(screen.getByRole('navigation', { name: '场景配置步骤' })).toBeTruthy()
    fireEvent.change(screen.getByPlaceholderText('如：企业信用风险联合研判'), { target: { value: '信用风险场景' } })
    fireEvent.click(screen.getByRole('button', { name: /行为设定/ }))
    fireEvent.change(screen.getByPlaceholderText(/严谨的金融分析师/), { target: { value: '综合多个智能体完成信用风险研判' } })
    fireEvent.click(screen.getByRole('button', { name: /协作编排/ }))
    fireEvent.click(screen.getByRole('button', { name: /创建草稿/ }))
    expect((await screen.findByRole('alert')).textContent).toContain('场景至少需要一个子智能体')
  })

  it('能力选择器分页展示并在搜索后回到匹配结果首页', async () => {
    mocks.listAvailable.mockResolvedValueOnce(Array.from({ length: 8 }, (_, index) => ({
      id: `skill-${index + 1}`,
      owner_id: 'owner-1',
      owner_name: '李老师',
      name: `分页 Skill ${index + 1}`,
      description: `第 ${index + 1} 个能力说明`,
      subject: '量化投资',
      visibility: 'private',
      call_count: index,
      version: 2,
      file_count: 1,
      total_bytes: 120,
      source: 'catalog',
      updated_at: '2026-08-14T00:00:00Z',
    })))
    const { container } = mount('/workspace/my-scenarios/create')
    fireEvent.click(screen.getByRole('button', { name: /能力组件/ }))

    expect(await screen.findByRole('group', { name: 'Skill 可选项' })).toBeTruthy()
    expect(screen.getAllByRole('checkbox')).toHaveLength(6)
    expect(screen.getByText('显示 1–6 / 8')).toBeTruthy()
    expect(screen.queryByRole('checkbox', { name: /分页 Skill 7/ })).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: 'Skill 下一页' }))
    const seventh = await screen.findByRole('checkbox', { name: /分页 Skill 7/ })
    expect(screen.getAllByRole('checkbox')).toHaveLength(2)
    fireEvent.click(seventh)
    expect(container.querySelector('.agent-builder-picker-selected')?.textContent).toBe('1已选')

    fireEvent.change(screen.getByRole('textbox', { name: '搜索 Skill 名称、作者或说明' }), { target: { value: '分页 Skill 8' } })
    expect(await screen.findByRole('checkbox', { name: /分页 Skill 8/ })).toBeTruthy()
    expect(screen.getByText('可用 8 项 · 匹配 1 项')).toBeTruthy()
    expect(screen.getByText('显示 1–1 / 1')).toBeTruthy()
    expect(screen.queryByRole('navigation', { name: 'Skill 分页' })).toBeNull()

    fireEvent.change(screen.getByRole('textbox', { name: '搜索 Skill 名称、作者或说明' }), { target: { value: '不存在的能力' } })
    expect((await screen.findByRole('status')).textContent).toBe('没有匹配项。')
    expect(screen.queryByRole('group', { name: 'Skill 可选项' })).toBeNull()
  })
})
