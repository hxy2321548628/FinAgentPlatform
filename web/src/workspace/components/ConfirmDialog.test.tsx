import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ConfirmDialog } from './ConfirmDialog'

afterEach(cleanup)

describe('ConfirmDialog', () => {
  it('open 时渲染标题与提示，初始焦点落在取消按钮', () => {
    render(<ConfirmDialog open title="删除会话" message="确认删除？此操作不可撤销。" onConfirm={vi.fn()} onCancel={vi.fn()} />)
    expect(screen.getByRole('alertdialog')).toBeTruthy()
    expect(screen.getByText('确认删除？此操作不可撤销。')).toBeTruthy()
    const cancel = screen.getByRole('button', { name: '取消' }) as HTMLButtonElement
    expect(document.activeElement).toBe(cancel)
  })

  it('Esc 触发 onCancel', () => {
    const onCancel = vi.fn()
    render(<ConfirmDialog open title="t" onConfirm={vi.fn()} onCancel={onCancel} />)
    fireEvent.keyDown(screen.getByRole('alertdialog'), { key: 'Escape' })
    expect(onCancel).toHaveBeenCalledOnce()
  })

  it('点击遮罩触发 onCancel，点击面板内部不触发', () => {
    const onCancel = vi.fn()
    const { container } = render(<ConfirmDialog open title="t" onConfirm={vi.fn()} onCancel={onCancel} />)
    const overlay = container.firstChild as HTMLElement
    fireEvent.click(overlay)
    expect(onCancel).toHaveBeenCalledOnce()
    fireEvent.click(screen.getByRole('alertdialog'))
    expect(onCancel).toHaveBeenCalledOnce()
  })

  it('Tab 焦点圈在面板内的两个按钮之间', () => {
    render(<ConfirmDialog open title="t" confirmLabel="删除" onConfirm={vi.fn()} onCancel={vi.fn()} />)
    const confirm = screen.getByRole('button', { name: '删除' }) as HTMLButtonElement
    const cancel = screen.getByRole('button', { name: '取消' }) as HTMLButtonElement
    confirm.focus()
    fireEvent.keyDown(screen.getByRole('alertdialog'), { key: 'Tab' })
    expect(document.activeElement).toBe(cancel)
    fireEvent.keyDown(screen.getByRole('alertdialog'), { key: 'Tab', shiftKey: true })
    expect(document.activeElement).toBe(confirm)
  })

  it('确认按钮触发 onConfirm', () => {
    const onConfirm = vi.fn()
    render(<ConfirmDialog open title="t" confirmLabel="删除" onConfirm={onConfirm} onCancel={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: '删除' }))
    expect(onConfirm).toHaveBeenCalledOnce()
  })

  it('未 open 时不渲染', () => {
    const { container } = render(<ConfirmDialog open={false} title="t" onConfirm={vi.fn()} onCancel={vi.fn()} />)
    expect(container.firstChild).toBeNull()
  })
})
