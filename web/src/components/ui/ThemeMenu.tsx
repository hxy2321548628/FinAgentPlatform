import { useEffect, useState } from 'react'
import { readThemeMode, saveThemeMode, subscribeTheme, type ThemeMode } from './theme'

/**
 * 主题循环按钮（公共顶栏与设置页共用）。
 *
 * 点击按「跟随系统 → 浅色 → 深色」循环；多个入口组件靠 theme.ts 的订阅机制同步。
 */

const MODES: ThemeMode[] = ['system', 'light', 'dark']

const MODE_LABEL: Record<ThemeMode, string> = {
  system: '跟随系统',
  light: '浅色',
  dark: '深色',
}

function ThemeIcon({ mode }: { mode: ThemeMode }) {
  if (mode === 'system') {
    return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><rect x="3" y="4" width="18" height="13" rx="2"/><path d="M8 21h8M12 17v4"/></svg>
  }
  if (mode === 'dark') {
    return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>
  }
  return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/></svg>
}

export function ThemeMenu({ showLabel = false }: { showLabel?: boolean }) {
  const [mode, setMode] = useState<ThemeMode>(readThemeMode)

  useEffect(() => subscribeTheme(() => setMode(readThemeMode())), [])

  const nextMode = MODES[(MODES.indexOf(mode) + 1) % MODES.length]
  const cycle = () => {
    saveThemeMode(nextMode)
    setMode(nextMode)
  }

  return (
    <button
      type="button"
      className={`theme-toggle${showLabel ? ' theme-toggle-labeled' : ''}`}
      aria-label={`切换外观（当前${MODE_LABEL[mode]}，点击切换为${MODE_LABEL[nextMode]}）`}
      title={`外观：${MODE_LABEL[mode]}；点击切换为${MODE_LABEL[nextMode]}`}
      onClick={cycle}
    >
      <ThemeIcon mode={mode} />
      {showLabel && <span>{MODE_LABEL[mode]}</span>}
    </button>
  )
}
