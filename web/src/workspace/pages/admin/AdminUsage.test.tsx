import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { UsageRanking } from '../../../api/types'
import { AdminUsage } from './AdminUsage'

const mocks = vi.hoisted(() => ({
  usageRanking: vi.fn<() => Promise<UsageRanking>>(),
}))

vi.mock('../../../api/usage', async importOriginal => ({
  ...(await importOriginal<typeof import('../../../api/usage')>()),
  usageRanking: mocks.usageRanking,
}))

afterEach(() => {
  cleanup()
  mocks.usageRanking.mockReset()
})

describe('AdminUsage', () => {
  it('用量排行每页十条且第二页延续真实排名', async () => {
    mocks.usageRanking.mockResolvedValue({
      available: true,
      total: { available: true, tokens: 66_000, cost: 6.6, observations: 66 },
      items: Array.from({ length: 11 }, (_, index) => ({
        user_id: `user-${index + 1}`,
        name: `排行用户 ${String(index + 1).padStart(2, '0')}`,
        tokens: (index + 1) * 1000,
        cost: index + 1,
        observations: index + 1,
      })),
    })

    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(<QueryClientProvider client={client}><AdminUsage /></QueryClientProvider>)

    expect(await screen.findByText('排行用户 01')).toBeTruthy()
    expect(screen.getAllByRole('row')).toHaveLength(11)
    expect(screen.queryByText('排行用户 11')).toBeNull()

    fireEvent.click(within(screen.getByRole('navigation', { name: '账号列表分页' })).getByRole('button', { name: '下一页' }))
    expect(screen.getByText('排行用户 11')).toBeTruthy()
    expect(screen.getByText('#11')).toBeTruthy()
  })
})
