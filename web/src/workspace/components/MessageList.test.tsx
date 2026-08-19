import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import type { InterruptAction } from '../../api/events'
import type { Decision } from '../../api/types'
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

describe('MessageList 提问与审批分流', () => {
  // 这一组同一段文案会渲染多次，不清干净上一次的 DOM 会撞上「找到多个」
  afterEach(cleanup)

  const question: InterruptAction = {
    index: 0,
    tool_name: 'ask_user_question',
    args: { question: '收益率按日频还是月频算？' },
    allowed_decisions: ['respond'],
  }
  const removal: InterruptAction = {
    index: 1,
    tool_name: 'delete',
    args: { file_path: '/workspace/raw.csv' },
    allowed_decisions: ['approve', 'reject', 'edit', 'respond'],
  }

  it('提问显示问题原文，不显示参数 JSON，也不摆一排只有一个选项的按钮', () => {
    render(<MessageList items={[]} pendingActions={[question]} onApprove={async () => {}} />)

    expect(screen.getByText('收益率按日频还是月频算？')).toBeTruthy()
    expect(screen.getByText('智能体在问你 1 个问题')).toBeTruthy()
    // 只允许 respond，决策已经替教师选好，输入框直接就在
    expect(screen.getByLabelText('回答第 1 个问题')).toBeTruthy()
    expect(screen.queryByText('回复智能体')).toBeNull()
    expect(document.body.textContent).not.toContain('ask_user_question')
  })

  it('审批照旧显示参数与四个决策按钮 —— 分流不能把闸门一起改掉', () => {
    render(<MessageList items={[]} pendingActions={[removal]} onApprove={async () => {}} />)

    expect(screen.getByText('智能体请求执行 1 个敏感操作')).toBeTruthy()
    expect(screen.getByText('允许执行')).toBeTruthy()
    expect(document.body.textContent).toContain('/workspace/raw.csv')
  })

  it('一次中断里既有提问又有审批时，两张卡片各是各的', () => {
    // `check()` 要求决策覆盖**全部** index，因此混合中断时教师必须能对每个
    // action 分别选 —— 少一个是 422，而那个红看着像 agent 没做好
    render(<MessageList items={[]} pendingActions={[question, removal]} onApprove={async () => {}} />)

    expect(screen.getByText('智能体在问你 1 个问题，另有 1 个敏感操作待确认')).toBeTruthy()
    expect(screen.getByText('收益率按日频还是月频算？')).toBeTruthy()
    expect(screen.getByLabelText('回答第 1 个问题')).toBeTruthy()
    expect(screen.getByText('允许执行')).toBeTruthy()
  })

  it('提问答完之后按 index 原样回传，且带着那句话', async () => {
    const sent: Decision[][] = []
    render(<MessageList items={[]} pendingActions={[question]} onApprove={async decisions => { sent.push(decisions) }} />)

    fireEvent.change(screen.getByLabelText('回答第 1 个问题'), { target: { value: '按月频' } })
    fireEvent.click(screen.getByText('提交回答'))
    await screen.findByText('提交回答')

    expect(sent).toEqual([[{ index: 0, type: 'respond', message: '按月频' }]])
  })
})
