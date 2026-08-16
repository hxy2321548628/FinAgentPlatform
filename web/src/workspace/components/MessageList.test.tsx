import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { RunViewItem } from '../eventReducer'
import { MessageList } from './MessageList'

describe('MessageList 分析思路单行收起', () => {
  it('默认收起；流式时思考内容以单行预览内联在标题行', () => {
    const items: RunViewItem[] = [{ kind: 'reasoning', text: '先计算对数收益率', path: [] }]

    const { rerender } = render(<MessageList items={items} />)

    const details = screen.getByText(/FinAgent · 分析思路/).closest('details') as HTMLDetailsElement
    expect(details.open).toBe(false)
    expect(document.querySelector('.reasoning-preview')).toBeNull()

    rerender(<MessageList items={items} live />)

    expect(details.open).toBe(false)
    expect(document.querySelector('.reasoning-preview')?.textContent).toBe('先计算对数收益率')

    fireEvent.click(screen.getByText(/FinAgent · 分析思路/))
    expect(details.open).toBe(true)
  })
})

describe('MessageList 助手头像', () => {
  it('用平台 Logo 而不是字母 F', () => {
    const items: RunViewItem[] = [{ kind: 'answer', text: '结论如下', path: [] }]

    render(<MessageList items={items} />)

    expect(screen.queryByText('F')).toBeNull()
    expect(document.querySelector('svg[viewBox="12 3 24 34"]')).toBeTruthy()
  })
})

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

describe('MessageList 未知工具', () => {
  it('一个平台从没见过的外部工具照常渲染出名字、参数与结果', () => {
    // **前端不认识 MCP 工具的名字，也不该认识。** 事件映射一行没改：外部工具的调用
    // 照常是 tool_call / tool_result，只是 name 是那台校外机器起的。若这里改成按
    // 已知工具名分支，接进来的第一个 MCP 就会在界面上「什么都不显示」而不报错。
    const items: RunViewItem[] = [
      {
        kind: 'tool',
        id: 'call-9',
        name: 'search_paper',
        args: { keyword: '随机波动率' },
        content: 'PAPER-HIT::随机波动率::《随机波动率模型的实证》',
        status: 'success',
        path: [],
      },
    ]

    render(<MessageList items={items} />)

    const toggle = screen.getByRole('button', { name: /search_paper/ })
    expect(toggle).toBeTruthy()
    fireEvent.click(toggle)
    expect(screen.getByText(/随机波动率模型的实证/)).toBeTruthy()
  })

  it('外部工具超时返回的错误结果标成失败而不是无声吞掉', () => {
    const items: RunViewItem[] = [
      {
        kind: 'tool',
        id: 'call-10',
        name: 'slow_query',
        args: { keyword: '沪深300' },
        content: '调用超时（30 秒），这个外部服务这次没有响应。',
        status: 'error',
        path: [],
      },
    ]

    render(<MessageList items={items} />)

    fireEvent.click(screen.getByRole('button', { name: /slow_query/ }))
    expect(screen.getByText(/调用超时/)).toBeTruthy()
  })
})
