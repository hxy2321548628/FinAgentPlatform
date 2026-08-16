import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ThemeMenu } from './ThemeMenu'

// jsdom 没有 matchMedia；theme 工具在 system 模式下要用它
vi.stubGlobal('matchMedia', vi.fn(() => ({
  matches: false,
  addEventListener: vi.fn(),
  removeEventListener: vi.fn(),
})))

afterEach(() => {
  cleanup()
  localStorage.clear()
  document.documentElement.classList.remove('dark')
  document.documentElement.style.colorScheme = ''
})

describe('ThemeMenu', () => {
  it('单击按跟随系统、浅色、深色循环并立即生效', () => {
    render(<ThemeMenu />)
    const button = screen.getByRole('button', { name: /当前跟随系统/ })

    fireEvent.click(button)
    expect(localStorage.getItem('finagent-theme')).toBe('light')
    expect(button.getAttribute('aria-label')).toContain('当前浅色')
    expect(document.documentElement.classList.contains('dark')).toBe(false)

    fireEvent.click(button)
    expect(localStorage.getItem('finagent-theme')).toBe('dark')
    expect(button.getAttribute('aria-label')).toContain('当前深色')
    expect(document.documentElement.classList.contains('dark')).toBe(true)

    fireEvent.click(button)
    expect(localStorage.getItem('finagent-theme')).toBe('system')
    expect(button.getAttribute('aria-label')).toContain('当前跟随系统')
    expect(document.documentElement.classList.contains('dark')).toBe(false)
  })

  it('设置页可直接显示当前模式文字', () => {
    localStorage.setItem('finagent-theme', 'dark')
    render(<ThemeMenu showLabel />)

    expect(screen.getByRole('button', { name: /当前深色/ }).textContent).toBe('深色')
  })
})
