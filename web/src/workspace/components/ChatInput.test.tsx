import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { AgentListing } from '../../api/types'
import { ChatInput } from './ChatInput'

const mocks = vi.hoisted(() => ({
  available: [] as AgentListing[],
  subagents: [] as AgentListing[],
  skills: [] as import('../../api/types').SkillListing[],
  mcps: [] as import('../../api/types').McpServer[],
}))

vi.mock('../../api/agents', async importOriginal => ({
  ...(await importOriginal<typeof import('../../api/agents')>()),
  listAvailable: () => Promise.resolve(mocks.available),
  listSubagentCandidates: () => Promise.resolve(mocks.subagents),
}))

vi.mock('../../api/skills', async importOriginal => ({
  ...(await importOriginal<typeof import('../../api/skills')>()),
  listAvailable: () => Promise.resolve(mocks.skills),
}))

vi.mock('../../api/mcp', async importOriginal => ({
  ...(await importOriginal<typeof import('../../api/mcp')>()),
  listCatalog: () => Promise.resolve(mocks.mcps),
}))

afterEach(() => {
  mocks.available = []
  mocks.subagents = []
  mocks.skills = []
  mocks.mcps = []
  cleanup()
})

function listing(overrides: Partial<AgentListing> = {}): AgentListing {
  return {
    id: 'agent-1',
    owner_id: 'u1',
    owner_name: '张老师',
    name: '喵语老师',
    description: '说话带喵',
    subject: '金融学',
    visibility: 'group',
    call_count: 3,
    version: 2,
    system_prompt: '每句以喵开头',
    source: 'group',
    updated_at: '2026-08-14T00:00:00Z',
    ...overrides,
  }
}

function mcpServer(overrides: Partial<import('../../api/types').McpServer> = {}): import('../../api/types').McpServer {
  return {
    id: 'mcp-1',
    name: '论文检索',
    description: '按关键词检索论文',
    url: 'https://mcp.example.edu/mcp',
    transport: 'streamable_http',
    has_credential: false,
    tool_names: ['search_paper'],
    latency_note: '1 秒',
    stores_user_data: false,
    sends_data_out: true,
    has_write_operation: false,
    status: 'enabled',
    disabled_reason: null,
    created_at: '2026-08-16T00:00:00Z',
    updated_at: '2026-08-16T00:00:00Z',
    ...overrides,
  }
}

function mount(props: Parameters<typeof ChatInput>[0]) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}><ChatInput {...props} /></QueryClientProvider>)
}

function input() {
  return screen.getByPlaceholderText('输入分析需求…（Enter 发送，Shift+Enter 换行）') as HTMLTextAreaElement
}

describe('ChatInput', () => {
  it('does not submit with Enter while a run is active', () => {
    const onSend = vi.fn(async () => {})
    mount({ isRunning: true, onSend })

    fireEvent.change(input(), { target: { value: '第二轮' } })
    fireEvent.keyDown(input(), { key: 'Enter' })

    expect(onSend).not.toHaveBeenCalled()
  })

  it('keeps the draft when submission fails', async () => {
    const onSend = vi.fn(async () => { throw new Error('提交失败') })
    mount({ onSend })

    fireEvent.change(input(), { target: { value: '保留这段输入' } })
    fireEvent.click(screen.getByRole('button', { name: '发送' }))

    await waitFor(() => expect(onSend).toHaveBeenCalledOnce())
    await waitFor(() => expect(input().disabled).toBe(false))
    expect(input().value).toBe('保留这段输入')
  })

  it('clears only after a successful submission and prevents duplicate sends', async () => {
    let resolve: (() => void) | undefined
    const pending = new Promise<void>(done => { resolve = done })
    const onSend = vi.fn(() => pending)
    mount({ onSend })

    fireEvent.change(input(), { target: { value: '只提交一次' } })
    fireEvent.keyDown(input(), { key: 'Enter' })
    fireEvent.keyDown(input(), { key: 'Enter' })

    expect(onSend).toHaveBeenCalledOnce()
    expect(input().value).toBe('只提交一次')
    resolve?.()
    await waitFor(() => expect(input().value).toBe(''))
  })

  it('sends only the reference when an agent is picked', async () => {
    // 同时带上 system_prompt 后端一律 422，而用户看到的是一句莫名其妙的报错
    mocks.available = [listing()]
    const onSend = vi.fn(async () => {})
    mount({ onSend })

    fireEvent.click(screen.getByRole('button', { name: /本轮智能体配置/ }))
    fireEvent.click(screen.getByLabelText('选一个智能体'))
    await waitFor(() => expect(screen.getByRole('option', { name: /喵语老师/ })).toBeTruthy())
    fireEvent.change(screen.getByLabelText('选择智能体'), { target: { value: 'agent-1' } })
    fireEvent.change(input(), { target: { value: '算个波动率' } })
    fireEvent.click(screen.getByRole('button', { name: '发送' }))

    await waitFor(() => expect(onSend).toHaveBeenCalledWith('算个波动率', { agent_id: 'agent-1' }))
  })

  it('refuses to submit an empty agent choice instead of letting the backend 422', async () => {
    mocks.available = [listing()]
    const onSend = vi.fn(async () => {})
    mount({ onSend })

    fireEvent.click(screen.getByRole('button', { name: /本轮智能体配置/ }))
    fireEvent.click(screen.getByLabelText('选一个智能体'))
    fireEvent.change(input(), { target: { value: '算个波动率' } })
    fireEvent.click(screen.getByRole('button', { name: '发送' }))

    await waitFor(() => expect(screen.getByRole('alert').textContent).toBe('请先选一个智能体'))
    expect(onSend).not.toHaveBeenCalled()
  })
})

describe('ChatInput Skills', () => {
  it('提交多选 Skill，并展示 Agent 自带与本轮 Skill 的合并结果', async () => {
    mocks.available = [listing({
      skill_refs: [{ skill_id: 'skill-agent', version: 2, name: 'agent-skill' }],
    })]
    mocks.skills = [
      { id: 'skill-agent', owner_id: 'u1', owner_name: '张老师', name: 'agent-skill', description: '自带', subject: '', visibility: 'group', call_count: 1, version: 2, file_count: 1, total_bytes: 10, source: 'group', updated_at: '2026-08-14T00:00:00Z' },
      { id: 'skill-turn', owner_id: 'u2', owner_name: '李老师', name: 'turn-skill', description: '本轮', subject: '', visibility: 'group', call_count: 2, version: 1, file_count: 1, total_bytes: 10, source: 'group', updated_at: '2026-08-14T00:00:00Z' },
    ]
    const onSend = vi.fn(async () => {})
    mount({ onSend })

    fireEvent.click(screen.getByRole('button', { name: /本轮智能体配置/ }))
    fireEvent.click(screen.getByLabelText('选一个智能体'))
    await waitFor(() => expect(screen.getByRole('option', { name: /喵语老师/ })).toBeTruthy())
    fireEvent.change(screen.getByLabelText('选择智能体'), { target: { value: 'agent-1' } })
    fireEvent.click(screen.getByLabelText('turn-skill'))

    expect(screen.getByText(/最终挂载：agent-skill、turn-skill/)).toBeTruthy()
    fireEvent.change(input(), { target: { value: '算个波动率' } })
    fireEvent.click(screen.getByRole('button', { name: '发送' }))

    await waitFor(() => expect(onSend).toHaveBeenCalledWith('算个波动率', {
      agent_id: 'agent-1',
      skills: ['skill-turn'],
    }))
  })
})


describe('ChatInput 子智能体', () => {
  it('展示主智能体自带与本轮选择的并集，并只提交本轮子智能体 ID', async () => {
    mocks.available = [listing({
      subagent_refs: [{ agent_id: 'child-bundled', version: 2, name: '内置波动率助手' }],
    })]
    mocks.subagents = [listing({ id: 'child-turn', name: '本轮收益率助手', version: 3 })]
    const onSend = vi.fn(async () => {})
    mount({ onSend })

    fireEvent.click(screen.getByRole('button', { name: /本轮智能体配置/ }))
    fireEvent.click(screen.getByLabelText('选一个智能体'))
    await waitFor(() => expect(screen.getByRole('option', { name: /喵语老师/ })).toBeTruthy())
    fireEvent.change(screen.getByLabelText('选择智能体'), { target: { value: 'agent-1' } })
    fireEvent.click(await screen.findByRole('checkbox', { name: /本轮收益率助手/ }))

    expect(screen.getByText(/最终挂载：内置波动率助手、本轮收益率助手/)).toBeTruthy()
    fireEvent.change(input(), { target: { value: '比较两种波动率' } })
    fireEvent.click(screen.getByRole('button', { name: '发送' }))

    await waitFor(() => expect(onSend).toHaveBeenCalledWith('比较两种波动率', {
      agent_id: 'agent-1',
      subagents: ['child-turn'],
    }))
  })

  it('直接勾一个 MCP 时看得见外发标注', async () => {
    mocks.mcps = [mcpServer()]
    mount({ onSend: vi.fn(async () => {}) })
    fireEvent.click(screen.getByRole('button', { name: '本轮智能体配置' }))

    fireEvent.click(await screen.findByRole('checkbox', { name: '论文检索' }))

    const notice = await screen.findByTestId('mcp-outbound')
    expect(notice.textContent).toContain('此服务位于校外，调用时你的数据会发送至外部')
    expect(notice.textContent).toContain('论文检索')
  })

  it('选一个自带 MCP 的子智能体时同样看得见，且说清它是谁带来的', async () => {
    // **F12 的组合风险就在这条路上**：教师一个 MCP 都没勾，而那个场景背后连着
    // 一台校外机器。漏掉这一条，风险就从「已缓解」退回「敞着」，而界面上看不出异样。
    mocks.mcps = [mcpServer()]
    mocks.subagents = [listing({ id: 'sub-1', name: '波动率专家', mcp_refs: [{ server_id: 'mcp-1', name: '论文检索' }] })]
    mount({ onSend: vi.fn(async () => {}) })
    fireEvent.click(screen.getByRole('button', { name: '本轮智能体配置' }))

    fireEvent.click(await screen.findByRole('checkbox', { name: '波动率专家' }))

    const notice = await screen.findByTestId('mcp-outbound')
    expect(notice.textContent).toContain('此服务位于校外，调用时你的数据会发送至外部')
    expect(notice.textContent).toContain('论文检索（来自 波动率专家）')
  })

  it('一个 MCP 都没有时不显示外发标注', async () => {
    mocks.mcps = [mcpServer()]
    mount({ onSend: vi.fn(async () => {}) })
    fireEvent.click(screen.getByRole('button', { name: '本轮智能体配置' }))
    await screen.findByRole('checkbox', { name: '论文检索' })

    expect(screen.queryByTestId('mcp-outbound')).toBeNull()
  })

  it('勾上的 MCP ID 随这一轮提交发出去', async () => {
    const onSend = vi.fn(async (_text: string, _config: import('../../api/types').AgentConfig | undefined) => {})
    mocks.mcps = [mcpServer()]
    mount({ onSend })
    fireEvent.click(screen.getByRole('button', { name: '本轮智能体配置' }))
    fireEvent.click(await screen.findByRole('checkbox', { name: '论文检索' }))
    fireEvent.click(screen.getByRole('button', { name: '完成' }))

    fireEvent.change(input(), { target: { value: '查一篇论文' } })
    fireEvent.keyDown(input(), { key: 'Enter' })

    await waitFor(() => expect(onSend).toHaveBeenCalled())
    expect(onSend.mock.calls[0][1]).toMatchObject({ mcps: ['mcp-1'] })
  })
})
