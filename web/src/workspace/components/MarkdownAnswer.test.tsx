import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { MarkdownAnswer } from './MarkdownAnswer'

// vitest 未开 globals，RTL 不会自动 cleanup —— 这里显式挂上，避免跨用例 DOM 串扰
afterEach(cleanup)

// jsdom 里跑真实 Shiki（JS 正则引擎，无 WASM）。只放少量断言依赖它，其余走同步渲染。

describe('MarkdownAnswer 结构渲染', () => {
  it('渲染标题、列表与表格', () => {
    render(<MarkdownAnswer text={'# 分析结论\n\n- 第一点\n- 第二点\n\n| 指标 | 数值 |\n| --- | --- |\n| 波动率 | 12% |'} />)
    expect(screen.getByRole('heading', { level: 1 })).toBeTruthy()
    expect(screen.getByText('第一点')).toBeTruthy()
    expect(screen.getByRole('table')).toBeTruthy()
    expect(screen.getByText('波动率')).toBeTruthy()
  })

  it('未闭合的代码围栏（流式常态）不抛错、按文本渲染', () => {
    render(<MarkdownAnswer text={'```python\nimport pandas' } streaming />)
    expect(screen.getByText(/import pandas/)).toBeTruthy()
  })
})

describe('MarkdownAnswer 公式边界（金融语境）', () => {
  it('$$ 块级公式渲染为 KaTeX', () => {
    const { container } = render(<MarkdownAnswer text={'推导如下：\n\n$$x^2 + y^2 = z^2$$'} />)
    expect(container.querySelector('.katex')).toBeTruthy()
  })

  it('金额 $32.5 不被当作行内公式', () => {
    const { container } = render(<MarkdownAnswer text={'股价 $32.5，成本 $1.2M。'} />)
    expect(container.querySelector('.katex')).toBeNull()
    expect(screen.getByText(/\$32\.5/)).toBeTruthy()
  })

  it('流式态不启用公式（未闭合 $$ 降级）', () => {
    const { container } = render(<MarkdownAnswer text={'$$\\frac{a}{b'} streaming />)
    expect(container.querySelector('.katex')).toBeNull()
  })
})

describe('MarkdownAnswer 图片路径', () => {
  it('outputs/ 相对路径重写为 raw URL', () => {
    render(<MarkdownAnswer threadId="t1" text={'![波动率图](outputs/chart.png)'} />)
    const img = screen.getByRole('img') as HTMLImageElement
    expect(img.src).toContain('/api/threads/t1/files/raw')
    expect(img.src).toContain('outputs%2Fchart.png')
  })

  it('目录逃逸路径不渲染图片，降级为文本', () => {
    const { container } = render(<MarkdownAnswer threadId="t1" text={'![../../etc/passwd](../../etc/passwd) 和 ![outputs/../secret.txt](outputs/../secret.txt)'} />)
    expect(container.querySelectorAll('img')).toHaveLength(0)
    expect(container.textContent).toContain('../../etc/passwd')
    expect(container.textContent).toContain('outputs/../secret.txt')
  })

  it('无 threadId 时不重写相对路径，降级为文本', () => {
    const { container } = render(<MarkdownAnswer text={'![outputs/chart.png](outputs/chart.png)'} />)
    expect(container.querySelectorAll('img')).toHaveLength(0)
    expect(container.textContent).toContain('outputs/chart.png')
  })

  it('http(s) 外链图片原样渲染', () => {
    render(<MarkdownAnswer text={'![外图](https://example.com/a.png)'} />)
    const img = screen.getByRole('img') as HTMLImageElement
    expect(img.src).toBe('https://example.com/a.png')
    // jsdom 不反射 loading 属性到 property，用 getAttribute 断言
    expect(img.getAttribute('loading')).toBe('lazy')
  })
})

describe('MarkdownAnswer 链接与 XSS 安全', () => {
  it('javascript: 协议被替换为不可点击', () => {
    render(<MarkdownAnswer text={'[点我](javascript:alert(1))'} />)
    const link = screen.getByRole('link') as HTMLAnchorElement
    expect(link.href.endsWith('#')).toBe(true)
  })

  it('http 链接保留并带 noopener', () => {
    render(<MarkdownAnswer text={'[说明](https://example.com/doc)'} />)
    const link = screen.getByRole('link') as HTMLAnchorElement
    expect(link.href).toBe('https://example.com/doc')
    expect(link.rel).toContain('noopener')
    expect(link.target).toBe('_blank')
  })

  it('原始 HTML 按文本渲染，不产生 DOM 注入', () => {
    const { container } = render(<MarkdownAnswer text={'<script>alert(1)</script><img src=x onerror=alert(2)>'} />)
    expect(container.querySelector('script')).toBeNull()
    expect(container.querySelectorAll('img')).toHaveLength(0)
    expect(screen.getByText(/alert\(1\)/)).toBeTruthy()
  })
})

describe('MarkdownAnswer 代码高亮', () => {
  it('终态时 python 围栏渲染为高亮代码', async () => {
    const { container } = render(<MarkdownAnswer text={'```python\nimport pandas as pd\nprint(1)\n```'} />)
    expect(container.querySelector('.code-block')).toBeTruthy()
    await waitFor(() => {
      expect(container.querySelector('[data-unhighlighted]')).toBeNull()
      expect(container.querySelector('.shiki')).toBeTruthy()
    })
  })

  it('流式态代码围栏先以未高亮纯文本渲染', () => {
    const { container } = render(<MarkdownAnswer text={'```python\nprint(1)'} streaming />)
    expect(container.querySelector('.code-block')).toBeTruthy()
    expect(container.querySelector('[data-unhighlighted]')).toBeTruthy()
  })

  it('白名单外语言降级为未高亮文本', async () => {
    const { container } = render(<MarkdownAnswer text={'```brainfuck\n+++[>++<-]>\n```'} />)
    expect(container.querySelector('.code-block')).toBeTruthy()
    // 等一拍，确认不会出现高亮结果
    await new Promise(resolve => setTimeout(resolve, 50))
    expect(container.querySelector('[data-unhighlighted]')).toBeTruthy()
  })
})
