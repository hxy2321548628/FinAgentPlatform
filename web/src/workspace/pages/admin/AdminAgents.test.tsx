import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { ReviewItem, UserRole } from '../../../api/types'
import { AdminAgents } from './AdminAgents'

const mocks = vi.hoisted(() => ({
  listReviews: vi.fn<() => Promise<ReviewItem[]>>(),
  decideReview: vi.fn(),
  setReviewCatalogEnabled: vi.fn(async () => ({})),
}))

vi.mock('../../../api/reviews', async importOriginal => ({
  ...(await importOriginal<typeof import('../../../api/reviews')>()),
  listReviews: mocks.listReviews,
  decideReview: mocks.decideReview,
  setReviewCatalogEnabled: mocks.setReviewCatalogEnabled,
}))

vi.mock('../../../api/auth', async importOriginal => ({
  ...(await importOriginal<typeof import('../../../api/auth')>()),
  me: vi.fn(async () => ({ id: 'u0', name: '管理员', email: 'admin@zuel.edu.cn', role: 'admin' as UserRole })),
}))

afterEach(() => {
  cleanup()
  mocks.listReviews.mockReset()
  mocks.decideReview.mockReset()
  mocks.setReviewCatalogEnabled.mockClear()
})

function review(index: number, status: ReviewItem['status']): ReviewItem {
  const suffix = String(index).padStart(2, '0')
  return {
    id: `${status}-${suffix}`,
    target_kind: 'agent',
    target_id: `version-${suffix}`,
    status,
    responsibility_confirmed: true,
    reason: status === 'rejected' ? `理由 ${suffix}` : null,
    created_at: '2026-08-18T00:00:00Z',
    decided_at: status === 'pending' ? null : '2026-08-18T01:00:00Z',
    owner_name: '周老师',
    description: '',
    subject: '公司金融',
    version: index,
    agent_id: `agent-${suffix}`,
    agent_name: `${status === 'pending' ? '待审智能体' : '处理记录'} ${suffix}`,
    system_prompt: `系统提示词 ${suffix}`,
    skill_refs: [],
    subagent_refs: [],
    mcp_refs: [],
    skill_id: null,
    skill_name: null,
    file_count: null,
    total_bytes: null,
    catalog_enabled: true,
    catalog_disabled_reason: null,
    catalog_disabled_by: null,
    catalog_disabled_at: null,
  }
}

function mount(records: ReviewItem[]) {
  mocks.listReviews.mockResolvedValue(records)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(<QueryClientProvider client={client}><AdminAgents /></QueryClientProvider>)
}

describe('AdminAgents', () => {
  it('重审核卡片每页两条，处理历史每页十条', async () => {
    mount([
      ...Array.from({ length: 3 }, (_, index) => review(index + 1, 'pending')),
      ...Array.from({ length: 11 }, (_, index) => review(index + 1, index % 3 === 0 ? 'rejected' : 'approved')),
    ])

    expect(await screen.findByText('待审智能体 01')).toBeTruthy()
    expect(screen.getAllByTestId('review-row')).toHaveLength(2)
    expect(screen.queryByText('待审智能体 03')).toBeNull()

    fireEvent.click(within(screen.getByRole('navigation', { name: '待审记录列表分页' })).getByRole('button', { name: '下一页' }))
    expect(screen.getByText('待审智能体 03')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: '最近处理 11' }))
    expect(screen.getAllByTestId('review-row')).toHaveLength(10)
    expect(screen.queryByText('处理记录 11')).toBeNull()
    const rejectedRow = screen.getByText('处理记录 01').closest('[data-testid="review-row"]')
    const approvedRow = screen.getByText('处理记录 02').closest('[data-testid="review-row"]')
    expect(rejectedRow).not.toBeNull()
    expect(approvedRow).not.toBeNull()
    expect(within(rejectedRow as HTMLElement).queryByRole('button', { name: '查看详情' })).toBeNull()
    expect(within(approvedRow as HTMLElement).getByRole('button', { name: '查看详情' })).toBeTruthy()

    fireEvent.click(within(screen.getByRole('navigation', { name: '处理记录列表分页' })).getByRole('button', { name: '下一页' }))
    expect(screen.getByText('处理记录 11')).toBeTruthy()
  })

  it('可查看场景冻结配置，管理员可填写原因后下架', async () => {
    const scenario = {
      ...review(1, 'pending'),
      agent_name: '企业风险研判',
      system_prompt: '你是企业风险分析助手',
      skill_refs: [{ skill_id: 'skill-1', version: 2, name: '财报分析' }],
      mcp_refs: [{ server_id: 'mcp-1', name: '工商数据' }],
      subagent_refs: [{ agent_id: 'agent-2', version: 3, name: '舆情分析' }],
    } satisfies ReviewItem
    const approved = { ...review(2, 'approved'), agent_name: '稳健性评估' } satisfies ReviewItem
    mount([scenario, approved])

    const pendingRow = await screen.findByTestId('review-row')
    expect(within(pendingRow).getByText('场景')).toBeTruthy()
    fireEvent.click(within(pendingRow).getByRole('button', { name: '查看详情' }))
    const detail = screen.getByRole('dialog')
    expect(within(detail).getByText('你是企业风险分析助手')).toBeTruthy()
    expect(within(detail).getByText('财报分析 · v2')).toBeTruthy()
    expect(within(detail).getByText('工商数据')).toBeTruthy()
    expect(within(detail).getByText('舆情分析 · v3')).toBeTruthy()
    fireEvent.click(within(detail).getByRole('button', { name: '关闭详情' }))

    fireEvent.click(screen.getByRole('button', { name: '最近处理 1' }))
    const decidedRow = screen.getByTestId('review-row')
    fireEvent.click(within(decidedRow).getByRole('button', { name: '下架' }))
    fireEvent.change(screen.getByPlaceholderText('请写明下架原因，作者会看到这段说明'), { target: { value: '配置已过期' } })
    fireEvent.click(screen.getByRole('button', { name: '确认下架' }))
    await waitFor(() => expect(mocks.setReviewCatalogEnabled).toHaveBeenCalledWith(approved.id, false, '配置已过期'))
  })
})
