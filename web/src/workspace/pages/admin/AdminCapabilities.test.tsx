import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { AdminMcpServer, UserRole } from '../../../api/types'
import { AUTH_QUERY_KEY } from '../../../api/auth'
import { AdminMcp, AdminSkills } from './AdminCapabilities'

const mocks = vi.hoisted(() => ({
  listReviews: vi.fn(async () => [{
    id: 'review-1', target_kind: 'skill', target_id: 'version-1', status: 'pending',
    responsibility_confirmed: true, reason: null, created_at: '2026-08-14T00:00:00Z', decided_at: null,
    owner_name: '周老师', description: '统一按 252 个交易日年化', subject: '量化投资', version: 3,
    agent_id: null, agent_name: null, system_prompt: null, skill_id: 'skill-1', skill_name: 'annualized-252',
    file_count: 2, total_bytes: 2048,
  }]),
  decideReview: vi.fn(async () => ({})),
  listForAdmin: vi.fn(async () => [] as AdminMcpServer[]),
  probe: vi.fn(
    async (): Promise<import('../../../api/types').McpProbe> =>
      ({ reachable: false, tool_names: [], declared_only: [], undeclared: [], failure_count: 5 }),
  ),
}))

vi.mock('../../../api/reviews', async importOriginal => ({
  ...(await importOriginal<typeof import('../../../api/reviews')>()),
  listReviews: mocks.listReviews,
  decideReview: mocks.decideReview,
}))

vi.mock('../../../api/auth', async importOriginal => ({
  ...(await importOriginal<typeof import('../../../api/auth')>()),
  me: vi.fn(async () => ({ id: 'u0', name: '某人', email: 'a@zuel.edu.cn', role: 'admin' as UserRole })),
}))

vi.mock('../../../api/mcp', async importOriginal => ({
  ...(await importOriginal<typeof import('../../../api/mcp')>()),
  listForAdmin: mocks.listForAdmin,
  probe: mocks.probe,
}))

afterEach(() => { cleanup(); mocks.listReviews.mockClear(); mocks.decideReview.mockClear(); mocks.listForAdmin.mockClear() })

function mcpRecord(overrides: Partial<AdminMcpServer> = {}): AdminMcpServer {
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
    submitted_by: 'u1',
    submitter_name: '周老师',
    failure_count: 0,
    ...overrides,
  }
}

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(<QueryClientProvider client={client}><AdminSkills /></QueryClientProvider>)
}

/** 挂 MCP 管理页。**身份要给全** —— 启停与探活按角色显隐，缺身份时它们一律不出现。 */
function mountMcp(role: UserRole = 'admin') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Number.POSITIVE_INFINITY }, mutations: { retry: false } },
  })
  client.setQueryData(AUTH_QUERY_KEY, { id: 'u0', name: '某人', email: 'a@zuel.edu.cn', role })
  return render(<QueryClientProvider client={client}><AdminMcp /></QueryClientProvider>)
}

describe('AdminSkills', () => {
  it('展示真实 Skill 审核元数据并要求拒绝理由', async () => {
    mount()
    expect(await screen.findByText('annualized-252')).toBeTruthy()
    expect(screen.getByText(/2 个文件/)).toBeTruthy()
    expect(screen.getByText(/2.0 KB/)).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: '拒绝' }))
    expect(screen.getByRole('alert').textContent).toContain('拒绝必须写明理由')
    expect(mocks.decideReview).not.toHaveBeenCalled()

    fireEvent.change(screen.getByRole('textbox', { name: /拒绝理由/ }), { target: { value: '说明不完整' } })
    fireEvent.click(screen.getByRole('button', { name: '拒绝' }))
    await waitFor(() => expect(mocks.decideReview).toHaveBeenCalledWith('review-1', false, '说明不完整'))
  })
})

describe('AdminMcp', () => {
  it('把熔断停用的那条标成「已自动停用」并显示原因', async () => {
    // **管理员总是最后一个知道**是 F5 修订版接受的代价：通知通道随可观测性一起撤了，
    // 剩下的降级手段只有日志与这一格标记 —— 它必须一眼看得出「不是我停的」。
    mocks.listForAdmin.mockResolvedValueOnce([
      mcpRecord({ status: 'disabled', disabled_reason: '连续失败 5 次，最后一次：连接失败：ExceptionGroup', failure_count: 5 }),
    ])
    mountMcp()

    expect(await screen.findByText('已自动停用')).toBeTruthy()
    expect(screen.getByText(/最后一次：连接失败/)).toBeTruthy()
    expect(screen.getByRole('button', { name: '恢复' })).toBeTruthy()
  })

  it('管理员手动停的那条不冒充自动停用', async () => {
    mocks.listForAdmin.mockResolvedValueOnce([
      mcpRecord({ status: 'disabled', disabled_reason: '管理员手动停用' }),
    ])
    mountMcp()

    expect(await screen.findByText('已停用')).toBeTruthy()
    expect(screen.queryByText('已自动停用')).toBeNull()
  })

  it('声明有写操作的那条在待审队列里标出「不可批」', async () => {
    mocks.listForAdmin.mockResolvedValueOnce([
      mcpRecord({ status: 'pending', has_write_operation: true }),
    ])
    mountMcp()

    expect(await screen.findByText('有写操作 · 不可批')).toBeTruthy()
  })

  it('测试连接把连不上与清单差异都摆出来', async () => {
    mocks.listForAdmin.mockResolvedValue([mcpRecord()])
    mocks.probe.mockResolvedValueOnce({ reachable: true, tool_names: ['search_paper', 'read_file'], declared_only: [], undeclared: ['read_file'], failure_count: 0 })
    mountMcp()

    fireEvent.click(await screen.findByRole('button', { name: '测试连接' }))

    await waitFor(() => expect(screen.getByText(/清单外多出：read_file/)).toBeTruthy())
  })

  /**
   * **审核员批得了 MCP，但停不了也探不了**（2026-08-16 起）。
   *
   * 边界从「按资源类型分」改成「按审核与运维分」：批与拒是审核，启停与探活是运维。
   * 后端对后两者回 403 —— 摆一个必然失败的按钮比不摆更糟，点下去只得到
   * 一句「需要管理员权限」，而页面看上去像是坏了。
   */
  it('审核员看得到批与拒，看不到启停与探活', async () => {
    mocks.listForAdmin.mockResolvedValue([mcpRecord({ status: 'pending' }), mcpRecord({ id: 'mcp-2', status: 'enabled' })])

    mountMcp('reviewer')

    expect(await screen.findByRole('button', { name: '通过' })).toBeTruthy()
    expect(screen.getByRole('button', { name: '拒绝' })).toBeTruthy()
    expect(screen.queryByRole('button', { name: '测试连接' })).toBeNull()
    expect(screen.queryByRole('button', { name: '停用' })).toBeNull()
  })

  it('管理员那两个运维按钮照旧在', async () => {
    mocks.listForAdmin.mockResolvedValue([mcpRecord({ id: 'mcp-2', status: 'enabled' })])

    mountMcp('admin')

    expect(await screen.findByRole('button', { name: '测试连接' })).toBeTruthy()
    expect(screen.getByRole('button', { name: '停用' })).toBeTruthy()
  })
})
