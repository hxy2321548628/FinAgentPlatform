import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { TodoItem } from '../../api/events'
import { TodoList } from './TodoList'

const THREE: TodoItem[] = [
  { content: '读取数据', status: 'completed' },
  { content: '算年化波动率', status: 'in_progress' },
  { content: '画柱状图', status: 'pending' },
]

describe('任务清单区', () => {
  it('报聚合读数并逐条列出，勾掉的那条有完成态', () => {
    render(<TodoList todos={THREE} />)

    expect(screen.getByText('已完成 1/3')).toBeTruthy()
    expect(screen.getByText('算年化波动率')).toBeTruthy()
    const items = document.querySelectorAll('[data-status]')
    expect([...items].map(one => one.getAttribute('data-status'))).toEqual(['completed', 'in_progress', 'pending'])
  })

  it('没有清单时整块不出现 —— 一句话就答完的问题不该多一个空面板', () => {
    const { container } = render(<TodoList todos={[]} />)

    expect(container.innerHTML).toBe('')
  })
})
