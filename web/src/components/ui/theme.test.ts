import { afterEach, describe, expect, it, vi } from 'vitest'
import { initTheme, readThemeMode, saveThemeMode } from './theme'

function fakeMatchMedia(dark: boolean) {
  const listeners = new Set<(event: MediaQueryListEvent) => void>()
  const mql = {
    matches: dark,
    addEventListener: vi.fn((_type: string, fn: (event: MediaQueryListEvent) => void) => listeners.add(fn)),
    removeEventListener: vi.fn(),
  }
  return { mql, listeners }
}

afterEach(() => {
  localStorage.clear()
  document.documentElement.classList.remove('dark')
  document.documentElement.style.colorScheme = ''
  vi.restoreAllMocks()
})

describe('theme 工具', () => {
  it('saveThemeMode 持久化并立即应用 class', () => {
    saveThemeMode('dark')
    expect(localStorage.getItem('finagent-theme')).toBe('dark')
    expect(document.documentElement.classList.contains('dark')).toBe(true)
    expect(document.documentElement.style.colorScheme).toBe('dark')

    saveThemeMode('light')
    expect(document.documentElement.classList.contains('dark')).toBe(false)
  })

  it('system 模式跟随 prefers-color-scheme', () => {
    const { mql } = fakeMatchMedia(true)
    vi.stubGlobal('matchMedia', vi.fn(() => mql))
    saveThemeMode('system')
    expect(document.documentElement.classList.contains('dark')).toBe(true)
  })

  it('readThemeMode 缺省为 system，非法值回落 system', () => {
    expect(readThemeMode()).toBe('system')
    localStorage.setItem('finagent-theme', 'oops')
    expect(readThemeMode()).toBe('system')
    localStorage.setItem('finagent-theme', 'dark')
    expect(readThemeMode()).toBe('dark')
  })

  it('initTheme 注册系统偏好监听：system 模式下随系统变化', () => {
    const { mql, listeners } = fakeMatchMedia(false)
    vi.stubGlobal('matchMedia', vi.fn(() => mql))
    localStorage.setItem('finagent-theme', 'system')
    initTheme()
    expect(document.documentElement.classList.contains('dark')).toBe(false)

    // 模拟系统切到深色
    mql.matches = true
    for (const fn of listeners) fn({ matches: true } as MediaQueryListEvent)
    expect(document.documentElement.classList.contains('dark')).toBe(true)
  })

  it('应用主题会同步 meta theme-color', () => {
    const meta = document.createElement('meta')
    meta.name = 'theme-color'
    document.head.appendChild(meta)
    saveThemeMode('dark')
    expect(meta.getAttribute('content')).toBe('#10141D')
    saveThemeMode('light')
    expect(meta.getAttribute('content')).toBe('#EDF0F5')
    meta.remove()
  })
})
