import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { AgentListing } from '../../api/types'
import { ChatInput } from './ChatInput'

const mocks = vi.hoisted(() => ({ available: [] as AgentListing[] }))

vi.mock('../../api/agents', async importOriginal => ({
  ...(await importOriginal<typeof import('../../api/agents')>()),
  listAvailable: () => Promise.resolve(mocks.available),
}))

afterEach(() => {
  mocks.available = []
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
    fireEvent.click(screen.getByTitle('发送'))

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
    fireEvent.click(screen.getByTitle('发送'))

    await waitFor(() => expect(onSend).toHaveBeenCalledWith('算个波动率', { agent_id: 'agent-1' }))
  })

  it('refuses to submit an empty agent choice instead of letting the backend 422', async () => {
    mocks.available = [listing()]
    const onSend = vi.fn(async () => {})
    mount({ onSend })

    fireEvent.click(screen.getByRole('button', { name: /本轮智能体配置/ }))
    fireEvent.click(screen.getByLabelText('选一个智能体'))
    fireEvent.change(input(), { target: { value: '算个波动率' } })
    fireEvent.click(screen.getByTitle('发送'))

    await waitFor(() => expect(screen.getByRole('alert').textContent).toBe('请先选一个智能体'))
    expect(onSend).not.toHaveBeenCalled()
  })
})
