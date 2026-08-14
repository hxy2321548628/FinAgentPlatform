import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ChatInput } from './ChatInput'

afterEach(cleanup)

function input() {
  return screen.getByPlaceholderText('输入分析需求…（Enter 发送，Shift+Enter 换行）') as HTMLTextAreaElement
}

describe('ChatInput', () => {
  it('does not submit with Enter while a run is active', () => {
    const onSend = vi.fn(async () => {})
    render(<ChatInput isRunning onSend={onSend} />)

    fireEvent.change(input(), { target: { value: '第二轮' } })
    fireEvent.keyDown(input(), { key: 'Enter' })

    expect(onSend).not.toHaveBeenCalled()
  })

  it('keeps the draft when submission fails', async () => {
    const onSend = vi.fn(async () => { throw new Error('提交失败') })
    render(<ChatInput onSend={onSend} />)

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
    render(<ChatInput onSend={onSend} />)

    fireEvent.change(input(), { target: { value: '只提交一次' } })
    fireEvent.keyDown(input(), { key: 'Enter' })
    fireEvent.keyDown(input(), { key: 'Enter' })

    expect(onSend).toHaveBeenCalledOnce()
    expect(input().value).toBe('只提交一次')
    resolve?.()
    await waitFor(() => expect(input().value).toBe(''))
  })
})
