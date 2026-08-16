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
/** 主题变化通知（多个入口组件靠它同步：Navbar / 设置页）。 */
export const THEME_EVENT = 'finagent-theme-changed'

export function readThemeMode(): ThemeMode {
  const stored = localStorage.getItem(STORAGE_KEY)
  return stored === 'light' || stored === 'dark' || stored === 'system' ? stored : 'system'
}

/** 当前真正生效的是深还是浅（system 模式下按系统偏好解析）。 */
export function effectiveIsDark(): boolean {
  return readThemeMode() === 'dark' || (readThemeMode() === 'system' && window.matchMedia(MEDIA).matches)
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
  window.dispatchEvent(new CustomEvent(THEME_EVENT))
}

/** 订阅主题变化（其他入口组件切换主题时同步自身 UI）。返回退订函数。 */
export function subscribeTheme(listener: () => void): () => void {
  window.addEventListener(THEME_EVENT, listener)
  return () => window.removeEventListener(THEME_EVENT, listener)
}

/** 应用启动时调用一次：恢复持久化选择并跟随系统变化（仅 system 模式响应）。 */
export function initTheme() {
  const stored = localStorage.getItem(STORAGE_KEY)
  const mode: ThemeMode = stored === 'light' || stored === 'dark' || stored === 'system' ? stored : 'system'
  applyTheme(mode)
  window.matchMedia(MEDIA).addEventListener('change', () => {
    if (readThemeMode() === 'system') {
      applyTheme('system')
      window.dispatchEvent(new CustomEvent(THEME_EVENT))
    }
  })
}
