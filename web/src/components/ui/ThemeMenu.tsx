import { useEffect, useState } from 'react'
import * as DropdownMenu from '@radix-ui/react-dropdown-menu'
import { effectiveIsDark, readThemeMode, saveThemeMode, subscribeTheme, type ThemeMode } from './theme'

/**
 * 主题切换菜单（公共顶栏与设置页共用）。
 *
 * 图标随「当前生效」的明暗变化（sun/moon），菜单三选一：浅色 / 深色 / 跟随系统。
 * 多个入口组件靠 theme.ts 的订阅机制同步，任何一处切换，其余入口立即跟上。
 */

const MODES: Array<{ value: ThemeMode; label: string }> = [
  { value: 'light', label: '浅色' },
  { value: 'dark', label: '深色' },
  { value: 'system', label: '跟随系统' },
]

export function ThemeMenu() {
  const [mode, setMode] = useState<ThemeMode>(readThemeMode)
  const [dark, setDark] = useState(effectiveIsDark)

  useEffect(() => subscribeTheme(() => {
    setMode(readThemeMode())
    setDark(effectiveIsDark())
  }), [])

  const choose = (value: ThemeMode) => {
    saveThemeMode(value)
    setMode(value)
    setDark(effectiveIsDark())
  }

  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <button
          type="button"
          className="theme-toggle"
          aria-label={`切换外观（当前${mode === 'system' ? '跟随系统' : mode === 'dark' ? '深色' : '浅色'}）`}
          title={`外观：${mode === 'system' ? '跟随系统' : mode === 'dark' ? '深色' : '浅色'}`}
        >
          {dark ? (
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>
          ) : (
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/></svg>
          )}
        </button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content className="theme-menu" sideOffset={6} align="end">
          {MODES.map(one => (
            <DropdownMenu.Item key={one.value} className="theme-menu-item" onSelect={() => choose(one.value)}>
              <span className="theme-menu-check" aria-hidden="true">{mode === one.value ? '✓' : ''}</span>
              {one.label}
            </DropdownMenu.Item>
          ))}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  )
}
