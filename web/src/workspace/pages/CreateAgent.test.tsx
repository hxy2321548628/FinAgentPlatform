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

afterEach(() => {
  cleanup()
  mocks.createAgent.mockClear()
  mocks.listAvailable.mockClear()
  mocks.listSubagentCandidates.mockClear()
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
  it('用分步工作台配置 Skill 与子智能体并创建草稿', async () => {
    mount()
    expect(screen.getByRole('navigation', { name: '智能体配置步骤' })).toBeTruthy()

    fireEvent.change(screen.getByPlaceholderText('如：企业财务异常检测'), { target: { value: '收益率助手' } })
    fireEvent.click(screen.getByRole('button', { name: /下一步/ }))
    fireEvent.change(screen.getByPlaceholderText(/严谨的金融分析师/), { target: { value: '请按统一口径计算收益率' } })
    fireEvent.click(screen.getByRole('button', { name: /下一步/ }))

    expect(await screen.findByText(/annualized-252/)).toBeTruthy()
    fireEvent.click(screen.getByRole('checkbox', { name: /annualized-252/ }))
    fireEvent.click(screen.getByRole('button', { name: /下一步/ }))
    fireEvent.click(await screen.findByRole('checkbox', { name: /波动率专家/ }))
    fireEvent.click(screen.getByRole('button', { name: /创建草稿/ }))

    await waitFor(() => expect(mocks.createAgent).toHaveBeenCalledWith(expect.objectContaining({
      skills: ['skill-1'],
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
})
