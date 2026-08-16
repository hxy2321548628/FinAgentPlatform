/**
 * 主题切换（DSD 第二章 §2.2 暗色色板）。
 *
 * 模式：'light' | 'dark' | 'system'。持久化在 localStorage('finagent-theme')，
 * 缺省跟随系统 prefers-color-scheme。挂在 <html class="dark"> 上（theme.css
 * 只认这一个作用域），并同步 <meta name="theme-color">。
 */

export type ThemeMode = 'light' | 'dark' | 'system'

const STORAGE_KEY = 'finagent-theme'
const MEDIA = '(prefers-color-scheme: dark)'

export function readThemeMode(): ThemeMode {
  const stored = localStorage.getItem(STORAGE_KEY)
  return stored === 'light' || stored === 'dark' || stored === 'system' ? stored : 'system'
}

export function applyTheme(mode: ThemeMode) {
  const dark = mode === 'dark' || (mode === 'system' && window.matchMedia(MEDIA).matches)
  document.documentElement.classList.toggle('dark', dark)
  document.documentElement.style.colorScheme = dark ? 'dark' : 'light'
  const themeColor = document.querySelector<HTMLMetaElement>('meta[name="theme-color"]')
  themeColor?.setAttribute('content', dark ? '#10141D' : '#EDF0F5')
}

export function saveThemeMode(mode: ThemeMode) {
  localStorage.setItem(STORAGE_KEY, mode)
  applyTheme(mode)
}

/** 应用启动时调用一次：恢复持久化选择并跟随系统变化（仅 system 模式响应）。 */
export function initTheme() {
  const stored = localStorage.getItem(STORAGE_KEY)
  const mode: ThemeMode = stored === 'light' || stored === 'dark' || stored === 'system' ? stored : 'system'
  applyTheme(mode)
  window.matchMedia(MEDIA).addEventListener('change', () => {
    if (readThemeMode() === 'system') applyTheme('system')
  })
}
