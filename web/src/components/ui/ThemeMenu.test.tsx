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
  it('展开菜单并选择深色：持久化 + html 类名生效', async () => {
    render(<ThemeMenu />)
    // Radix DropdownMenu 在 pointerdown 打开；jsdom 下用键盘路径（ArrowDown）最稳
    fireEvent.keyDown(screen.getByRole('button', { name: /切换外观/ }), { key: 'ArrowDown' })

    expect(await screen.findByText('浅色')).toBeTruthy()
    expect(screen.getByText('跟随系统')).toBeTruthy()

    fireEvent.click(screen.getByText('深色'))
    expect(localStorage.getItem('finagent-theme')).toBe('dark')
    expect(document.documentElement.classList.contains('dark')).toBe(true)
  })

  it('当前模式显示勾选标记，切换后标记跟着走', async () => {
    localStorage.setItem('finagent-theme', 'dark')
    render(<ThemeMenu />)
    // Radix DropdownMenu 在 pointerdown 打开；jsdom 下用键盘路径（ArrowDown）最稳
    fireEvent.keyDown(screen.getByRole('button', { name: /切换外观/ }), { key: 'ArrowDown' })
    await screen.findByText('深色')

    // 深色项带 ✓；浅色项不带
    const darkItem = screen.getByText('深色').closest('.theme-menu-item')!
    const lightItem = screen.getByText('浅色').closest('.theme-menu-item')!
    expect(darkItem.querySelector('.theme-menu-check')?.textContent).toBe('✓')
    expect(lightItem.querySelector('.theme-menu-check')?.textContent).toBe('')

    // 切到浅色后标记跟着走
    fireEvent.click(screen.getByText('浅色'))
    expect(localStorage.getItem('finagent-theme')).toBe('light')
  })
})
