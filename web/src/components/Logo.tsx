/**
 * 平台 LOGO（DSD §6）：学院塔形图标 + 可选文字，图标 SVG 只此一份。
 *
 * 用法：`<Logo height={24} />` 亮底用默认院徽绿；深色背景传 `color="#fff"`。
 * 替换此前在 Navbar / Footer / Login / WorkspaceSidebar / AdminLayout 里的五份复制。
 */

const LOGO_PATH_1 = 'M24.22,27.73l1.05-2c.36-.69.73-1.38,1.08-2.07a.26.26,0,0,1,.27-.17h3.83a.26.26,0,0,1,.27.18c1.44,3.06,3,6.08,4.65,9a.23.23,0,0,0,.08.16H27.09a.3.3,0,0,1-.32-.19q-1.2-2.34-2.42-4.66l-.14-.25c-.05.09-.1.16-.13.23l-2.44,4.7a.25.25,0,0,1-.26.17H13l.4-.83c1.53-2.72,2.94-5.5,4.27-8.33a.35.35,0,0,1,.38-.24h3.74a.27.27,0,0,1,.28.18l2,3.84Z'
const LOGO_PATH_2 = 'M24.21,4.19a82.908,82.908,0,0,0,2.43,9.16,85.1,85.1,0,0,0,3.43,8.85H18.33a79,79,0,0,0,3.47-8.86,84.311,84.311,0,0,0,2.41-9.15Zm0,16.18A1.3,1.3,0,1,0,23,19.07a1.26,1.26,0,0,0,1.23,1.3Z'

interface LogoProps {
  height?: number
  /** 亮底默认 `var(--logo-green)`；深色背景传 `#fff`（DSD §6 反白规则）。 */
  color?: string
  className?: string
}

export function Logo({ height = 24, color = 'var(--logo-green)', className }: LogoProps) {
  return (
    <svg viewBox="12 3 24 34" fill="currentColor" aria-hidden="true" className={className} style={{ height, width: 'auto', color, flexShrink: 0 }}>
      <path d={LOGO_PATH_1} />
      <path d={LOGO_PATH_2} />
    </svg>
  )
}
