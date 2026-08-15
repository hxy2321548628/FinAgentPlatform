import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { RunViewItem } from '../eventReducer'
import { MessageList } from './MessageList'

describe('MessageList 子智能体折叠块', () => {
  it('按 path 收起嵌套过程，并用子智能体名作为标题', () => {
    const items: RunViewItem[] = [
      { kind: 'answer', text: '主智能体开始', path: [] },
      { kind: 'reasoning', text: '先计算波动率', path: ['volatility-expert'] },
      {
        kind: 'tool',
        id: 'call-1',
        name: 'write_file',
        args: { file_path: '/workspace/outputs/result.txt' },
        content: 'Wrote file',
        status: 'success',
        path: ['volatility-expert'],
      },
      { kind: 'answer', text: '子任务完成', path: ['volatility-expert'] },
      { kind: 'answer', text: '主智能体总结', path: [] },
    ]

    render(<MessageList items={items} />)

    const title = screen.getByText('volatility-expert')
    const details = title.closest('details') as HTMLDetailsElement
    expect(details.open).toBe(false)
    expect(within(details).getByText('write_file')).toBeTruthy()
    expect(within(details).getByText('子任务完成')).toBeTruthy()
    expect(within(details).queryByText('主智能体总结')).toBeNull()

    fireEvent.click(title)
    expect(details.open).toBe(true)
  })
})
