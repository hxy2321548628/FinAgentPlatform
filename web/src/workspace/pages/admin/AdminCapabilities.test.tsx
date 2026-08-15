import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AdminSkills } from './AdminCapabilities'

const mocks = vi.hoisted(() => ({
  listReviews: vi.fn(async () => [{
    id: 'review-1', target_kind: 'skill', target_id: 'version-1', status: 'pending',
    responsibility_confirmed: true, reason: null, created_at: '2026-08-14T00:00:00Z', decided_at: null,
    owner_name: '周老师', description: '统一按 252 个交易日年化', subject: '量化投资', version: 3,
    agent_id: null, agent_name: null, system_prompt: null, skill_id: 'skill-1', skill_name: 'annualized-252',
    file_count: 2, total_bytes: 2048,
  }]),
  decideReview: vi.fn(async () => ({})),
}))

vi.mock('../../../api/reviews', async importOriginal => ({
  ...(await importOriginal<typeof import('../../../api/reviews')>()),
  listReviews: mocks.listReviews,
  decideReview: mocks.decideReview,
}))

afterEach(() => { cleanup(); mocks.listReviews.mockClear(); mocks.decideReview.mockClear() })

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(<QueryClientProvider client={client}><AdminSkills /></QueryClientProvider>)
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
