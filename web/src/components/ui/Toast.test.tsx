import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { ToastProvider } from './Toast'
import { useToast } from './toast-context'

afterEach(cleanup)

function Harness({ title, variant }: { title: string; variant?: 'success' | 'error' }) {
  const { toast } = useToast()
  return <button type="button" onClick={() => toast({ title, variant })}>触发</button>
}

describe('Toast', () => {
  it('toast() 调用后出现标题，并可手动关闭', async () => {
    render(
      <ToastProvider>
        <Harness title="文件已保存" />
      </ToastProvider>,
    )
    fireEvent.click(screen.getByRole('button', { name: '触发' }))
    expect(await screen.findByText('文件已保存')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '关闭通知' }))
    expect(screen.queryByText('文件已保存')).toBeNull()
  })

  it('错误与成功变体带上对应 class', async () => {
    render(
      <ToastProvider>
        <Harness title="保存失败" variant="error" />
      </ToastProvider>,
    )
    fireEvent.click(screen.getByRole('button', { name: '触发' }))
    const root = (await screen.findByText('保存失败')).closest('.toast')
    expect(root?.className).toContain('toast-error')
  })

  it('连续触发只保留最近三条', async () => {
    render(
      <ToastProvider>
        <Harness title="a" />
      </ToastProvider>,
    )
    const fire = () => fireEvent.click(screen.getByRole('button', { name: '触发' }))
    fire()
    fire()
    fire()
    fire()
    expect(await screen.findAllByText('a')).toHaveLength(3)
  })
})
