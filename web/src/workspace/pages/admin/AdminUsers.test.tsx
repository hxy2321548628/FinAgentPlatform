import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { AdminUser } from '../../../api/types'
import { AdminUsers } from './AdminUsers'

const mocks = vi.hoisted(() => ({
  listUsers: vi.fn<() => Promise<AdminUser[]>>(),
  createUser: vi.fn(),
  updateUser: vi.fn(),
}))

vi.mock('../../../api/admin', async importOriginal => ({
  ...(await importOriginal<typeof import('../../../api/admin')>()),
  listUsers: mocks.listUsers,
  createUser: mocks.createUser,
  updateUser: mocks.updateUser,
}))

afterEach(() => {
  cleanup()
  mocks.listUsers.mockReset()
  mocks.createUser.mockReset()
  mocks.updateUser.mockReset()
})

function user(index: number, active = true): AdminUser {
  const suffix = String(index).padStart(2, '0')
  return {
    id: `${active ? 'active' : 'pending'}-${suffix}`,
    name: `${active ? '活跃' : '待激活'}账号 ${suffix}`,
    email: `${active ? 'active' : 'pending'}-${suffix}@zuel.edu.cn`,
    dept: '金融学院',
    role: 'teacher',
    is_active: active,
    quota_tokens_daily: null,
    quota_concurrent_runs: null,
  }
}

function open(users: AdminUser[]) {
  mocks.listUsers.mockResolvedValue(users)
  mocks.updateUser.mockImplementation(async (id: string, body: Partial<AdminUser>) => ({
    ...users.find(one => one.id === id)!,
    ...body,
  }))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(<QueryClientProvider client={client}><AdminUsers /></QueryClientProvider>)
}

describe('AdminUsers', () => {
  it('用单表格、快捷筛选和分页承载长账号列表', async () => {
    const users = [user(1, false), user(2, false), ...Array.from({ length: 25 }, (_, index) => user(index + 1))]
    open(users)

    expect(await screen.findByText('活跃账号 01')).toBeTruthy()
    expect(screen.getAllByRole('table')).toHaveLength(1)
    expect(screen.getByText('显示 1–10 项，共 27 个账号')).toBeTruthy()
    expect(screen.queryByText('活跃账号 25')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: '下一页' }))
    expect(screen.getByText('活跃账号 09')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: '待激活 2' }))
    expect(screen.getAllByRole('row')).toHaveLength(3)
    expect(screen.getByText('待激活账号 01')).toBeTruthy()
    expect(screen.queryByText('活跃账号 01')).toBeNull()

    fireEvent.change(screen.getByRole('searchbox', { name: '搜索账号' }), { target: { value: 'pending-02@zuel.edu.cn' } })
    expect(screen.queryByText('待激活账号 01')).toBeNull()
    expect(screen.getByText('待激活账号 02')).toBeTruthy()
  })

  it('停用账号前明确说明影响并要求确认', async () => {
    open([user(1)])

    const row = await screen.findByRole('row', { name: /活跃账号 01/ })
    fireEvent.click(within(row).getByRole('button', { name: '停用' }))

    expect(screen.getByRole('alertdialog')).toBeTruthy()
    expect(screen.getByText(/无法登录或发起分析/)).toBeTruthy()
    expect(mocks.updateUser).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: '确认停用' }))

    await waitFor(() => expect(mocks.updateUser).toHaveBeenCalledWith('active-01', { is_active: false }))
  })
})
