import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { AdminMcpServer, ReviewItem, UserRole } from '../../../api/types'
import { AUTH_QUERY_KEY } from '../../../api/auth'
import { AdminMcp, AdminSkills } from './AdminCapabilities'

const mocks = vi.hoisted(() => ({
  listReviews: vi.fn<() => Promise<ReviewItem[]>>(async () => [{
    id: 'review-1', target_kind: 'skill', target_id: 'version-1', status: 'pending',
    responsibility_confirmed: true, reason: null, created_at: '2026-08-14T00:00:00Z', decided_at: null,
    owner_name: '周老师', description: '统一按 252 个交易日年化', subject: '量化投资', version: 3,
    agent_id: null, agent_name: null, system_prompt: null, skill_id: 'skill-1', skill_name: 'annualized-252',
    skill_refs: [], subagent_refs: [], mcp_refs: [], file_count: 2, total_bytes: 2048,
    catalog_enabled: true, catalog_disabled_reason: null, catalog_disabled_by: null, catalog_disabled_at: null,
  }]),
  decideReview: vi.fn(async () => ({})),
  listReviewSkillFiles: vi.fn(async () => [{ path: 'SKILL.md', size: 32 }]),
  readReviewSkillFile: vi.fn(async () => ({ path: 'SKILL.md', size: 32, content: '# 年化收益率\n统一按 252 个交易日年化。', is_binary: false })),
  setReviewCatalogEnabled: vi.fn(async () => ({})),
  listForAdmin: vi.fn(async () => [] as AdminMcpServer[]),
  decideApplication: vi.fn(async () => ({})),
  setEnabled: vi.fn(async () => ({})),
  probe: vi.fn(
    async (): Promise<import('../../../api/types').McpProbe> =>
      ({ reachable: false, tool_names: [], declared_only: [], undeclared: [], failure_count: 5 }),
  ),
}))

vi.mock('../../../api/reviews', async importOriginal => ({
  ...(await importOriginal<typeof import('../../../api/reviews')>()),
  listReviews: mocks.listReviews,
  decideReview: mocks.decideReview,
  listReviewSkillFiles: mocks.listReviewSkillFiles,
  readReviewSkillFile: mocks.readReviewSkillFile,
  setReviewCatalogEnabled: mocks.setReviewCatalogEnabled,
}))

vi.mock('../../../api/auth', async importOriginal => ({
  ...(await importOriginal<typeof import('../../../api/auth')>()),
  me: vi.fn(async () => ({ id: 'u0', name: '某人', email: 'a@zuel.edu.cn', role: 'admin' as UserRole })),
}))

vi.mock('../../../api/mcp', async importOriginal => ({
  ...(await importOriginal<typeof import('../../../api/mcp')>()),
  listForAdmin: mocks.listForAdmin,
  decideApplication: mocks.decideApplication,
  setEnabled: mocks.setEnabled,
  probe: mocks.probe,
}))

afterEach(() => {
  cleanup()
  mocks.listReviews.mockClear()
  mocks.decideReview.mockClear()
  mocks.listReviewSkillFiles.mockClear()
  mocks.readReviewSkillFile.mockClear()
  mocks.setReviewCatalogEnabled.mockClear()
  mocks.listForAdmin.mockClear()
  mocks.decideApplication.mockClear()
  mocks.setEnabled.mockClear()
  mocks.probe.mockClear()
})

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

function skillReview(index: number, status: ReviewItem['status'] = 'approved'): ReviewItem {
  const suffix = String(index).padStart(2, '0')
  return {
    id: `skill-review-${suffix}`,
    target_kind: 'skill',
    target_id: `skill-version-${suffix}`,
    status,
    responsibility_confirmed: true,
    reason: status === 'rejected' ? `拒绝理由 ${suffix}` : null,
    created_at: '2026-08-18T00:00:00Z',
    decided_at: status === 'pending' ? null : '2026-08-18T01:00:00Z',
    owner_name: '周老师',
    description: `Skill 描述 ${suffix}`,
    subject: '量化投资',
    version: index,
    agent_id: null,
    agent_name: null,
    system_prompt: null,
    skill_refs: [],
    subagent_refs: [],
    mcp_refs: [],
    skill_id: `skill-${suffix}`,
    skill_name: `分页 Skill ${suffix}`,
    file_count: 2,
    total_bytes: 2048,
    catalog_enabled: true,
    catalog_disabled_reason: null,
    catalog_disabled_by: null,
    catalog_disabled_at: null,
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

  it('待审与最近处理分开显示，详情历史每页八条', async () => {
    mocks.listReviews.mockResolvedValueOnce(Array.from({ length: 11 }, (_, index) => skillReview(index + 1)))
    mount()

    fireEvent.click(await screen.findByRole('button', { name: '最近处理 11' }))
    expect(screen.getAllByTestId('review-row')).toHaveLength(8)
    expect(screen.queryByText('分页 Skill 11')).toBeNull()

    fireEvent.click(within(screen.getByRole('navigation', { name: '处理记录列表分页' })).getByRole('button', { name: '下一页' }))
    expect(screen.getByText('分页 Skill 11')).toBeTruthy()
  })

  it('已拒绝 Skill 保留原因但不再提供查看入口', async () => {
    const approved = { ...skillReview(1), skill_name: '已通过 Skill' } satisfies ReviewItem
    const rejected = { ...skillReview(2, 'rejected'), skill_name: '已拒绝 Skill' } satisfies ReviewItem
    mocks.listReviews.mockResolvedValueOnce([approved, rejected])
    mount()

    fireEvent.click(await screen.findByRole('button', { name: '最近处理 2' }))
    const rows = screen.getAllByTestId('review-row')
    expect(within(rows[0]).getByRole('button', { name: '查看' })).toBeTruthy()
    expect(within(rows[1]).queryByRole('button', { name: '查看' })).toBeNull()
    expect(within(rows[1]).getByText(/拒绝理由 02/)).toBeTruthy()
  })

  it('待审与已通过 Skill 都可查看版本文件，管理员可填写原因后下架', async () => {
    const pending = skillReview(1, 'pending')
    const approved = { ...skillReview(2), skill_name: '已上架 Skill' } satisfies ReviewItem
    mocks.listReviews.mockResolvedValueOnce([pending, approved])
    mount()

    const pendingRow = await screen.findByTestId('review-row')
    fireEvent.click(within(pendingRow).getByRole('button', { name: '查看' }))
    const detail = screen.getByRole('dialog')
    expect(detail.classList.contains('skill-browser-drawer')).toBe(true)
    expect(await within(detail).findByRole('button', { name: /SKILL\.md/ })).toBeTruthy()
    expect(await within(detail).findByText(/252 个交易日年化/)).toBeTruthy()
    expect(within(detail).getByLabelText('只读代码查看器')).toBeTruthy()
    expect(within(detail).queryByRole('button', { name: /使用 Skill/ })).toBeNull()
    fireEvent.click(within(detail).getByRole('button', { name: '关闭' }))

    fireEvent.click(screen.getByRole('button', { name: '最近处理 1' }))
    const decidedRow = screen.getByTestId('review-row')
    fireEvent.click(within(decidedRow).getByRole('button', { name: '下架' }))
    fireEvent.change(screen.getByPlaceholderText('请写明下架原因，作者会看到这段说明'), { target: { value: '内容已过期' } })
    fireEvent.click(screen.getByRole('button', { name: '确认下架' }))
    await waitFor(() => expect(mocks.setReviewCatalogEnabled).toHaveBeenCalledWith(approved.id, false, '内容已过期'))
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

    fireEvent.click(await screen.findByRole('button', { name: '已放行 1' }))
    expect(await screen.findByText('已自动停用')).toBeTruthy()
    expect(screen.getByText(/最后一次：连接失败/)).toBeTruthy()
    expect(screen.getByRole('button', { name: '查看' })).toBeTruthy()
    expect(screen.getByRole('button', { name: '恢复上架' })).toBeTruthy()
  })

  it('管理员手动停的那条不冒充自动停用', async () => {
    mocks.listForAdmin.mockResolvedValueOnce([
      mcpRecord({ status: 'disabled', disabled_reason: '管理员手动停用' }),
    ])
    mountMcp()

    fireEvent.click(await screen.findByRole('button', { name: '已放行 1' }))
    expect(await screen.findByText('已停用')).toBeTruthy()
    expect(screen.queryByText('已自动停用')).toBeNull()
  })

  it('声明有写操作的那条在待审队列里标出「不可批」', async () => {
    mocks.listForAdmin.mockResolvedValueOnce([
      mcpRecord({ status: 'pending', has_write_operation: true }),
    ])
    mountMcp()

    expect(await screen.findByText('有写操作 · 不可批')).toBeTruthy()
    expect(screen.getByRole('button', { name: '查看' })).toBeTruthy()
  })

  it('测试连接把连不上与清单差异都摆出来', async () => {
    mocks.listForAdmin.mockResolvedValue([mcpRecord()])
    mocks.probe.mockResolvedValueOnce({ reachable: true, tool_names: ['search_paper', 'read_file'], declared_only: [], undeclared: ['read_file'], failure_count: 0 })
    mountMcp()

    fireEvent.click(await screen.findByRole('button', { name: '已放行 1' }))
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
    fireEvent.click(screen.getByRole('button', { name: '已放行 1' }))
    expect(screen.queryByRole('button', { name: '测试连接' })).toBeNull()
    expect(screen.queryByRole('button', { name: '下架' })).toBeNull()
  })

  it('管理员那两个运维按钮照旧在', async () => {
    mocks.listForAdmin.mockResolvedValue([mcpRecord({ id: 'mcp-2', status: 'enabled' })])

    mountMcp('admin')

    fireEvent.click(await screen.findByRole('button', { name: '已放行 1' }))
    expect(await screen.findByRole('button', { name: '测试连接' })).toBeTruthy()
    expect(screen.getByRole('button', { name: '下架' })).toBeTruthy()
  })

  it('可查看 MCP 完整声明，下架时要求原因', async () => {
    mocks.listForAdmin.mockResolvedValueOnce([mcpRecord()])
    mountMcp()

    fireEvent.click(await screen.findByRole('button', { name: '已放行 1' }))
    const row = screen.getByTestId('mcp-row')
    fireEvent.click(within(row).getByRole('button', { name: '查看' }))
    const detail = screen.getByRole('dialog')
    expect(detail.classList.contains('dialog-drawer')).toBe(true)
    expect(within(detail).getByText('https://mcp.example.edu/mcp')).toBeTruthy()
    expect(within(detail).getByText('search_paper')).toBeTruthy()
    expect(within(detail).getByText('声明会转发给第三方')).toBeTruthy()
    expect(within(detail).queryByRole('button', { name: /使用 MCP/ })).toBeNull()
    fireEvent.click(within(detail).getByRole('button', { name: '关闭' }))

    fireEvent.click(within(row).getByRole('button', { name: '下架' }))
    expect((screen.getByRole('button', { name: '确认下架' }) as HTMLButtonElement).disabled).toBe(true)
    fireEvent.change(screen.getByPlaceholderText('请写明下架原因，作者会看到这段说明'), { target: { value: '服务安全策略变更' } })
    fireEvent.click(screen.getByRole('button', { name: '确认下架' }))
    await waitFor(() => expect(mocks.setEnabled).toHaveBeenCalledWith('mcp-1', false, '服务安全策略变更'))
  })

  it('待审、已放行和已拒绝各自分页且一次只展示一种状态', async () => {
    mocks.listForAdmin.mockResolvedValueOnce([
      ...Array.from({ length: 6 }, (_, index) => mcpRecord({ id: `pending-${index + 1}`, name: `待审 MCP ${String(index + 1).padStart(2, '0')}`, status: 'pending' })),
      ...Array.from({ length: 11 }, (_, index) => mcpRecord({ id: `live-${index + 1}`, name: `放行 MCP ${String(index + 1).padStart(2, '0')}`, status: 'enabled' })),
      ...Array.from({ length: 11 }, (_, index) => mcpRecord({ id: `closed-${index + 1}`, name: `拒绝 MCP ${String(index + 1).padStart(2, '0')}`, status: 'rejected', disabled_reason: '资料不完整' })),
    ])
    mountMcp()

    expect(await screen.findByText('待审 MCP 01')).toBeTruthy()
    expect(screen.getAllByTestId('mcp-row')).toHaveLength(5)
    expect(screen.queryByText('待审 MCP 06')).toBeNull()
    expect(screen.queryByText('放行 MCP 01')).toBeNull()

    fireEvent.click(within(screen.getByRole('navigation', { name: '待审 MCP列表分页' })).getByRole('button', { name: '下一页' }))
    expect(screen.getByText('待审 MCP 06')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: '已放行 11' }))
    expect(screen.getAllByTestId('mcp-row')).toHaveLength(8)
    expect(screen.queryByText('放行 MCP 11')).toBeNull()
    expect(screen.queryByText('待审 MCP 06')).toBeNull()

    fireEvent.click(within(screen.getByRole('navigation', { name: '已放行 MCP列表分页' })).getByRole('button', { name: '下一页' }))
    expect(screen.getByText('放行 MCP 11')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: '已拒绝 11' }))
    expect(screen.getAllByTestId('mcp-row')).toHaveLength(8)
    expect(screen.queryByText('拒绝 MCP 11')).toBeNull()
    expect(screen.queryByRole('button', { name: '查看' })).toBeNull()
    expect(screen.getAllByText('资料不完整')).toHaveLength(8)
  })
})
