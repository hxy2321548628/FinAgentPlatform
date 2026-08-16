import type { ButtonHTMLAttributes } from 'react'

/**
 * 基础按钮（DSD 第二章 §2.9 / P1 b1 组件层第一步）。
 *
 * 视觉全部走 theme.css 的 .btn-*；本组件只负责变体与语义默认值。
 * 迁移策略：新代码与弹窗/表单用本组件，存量内联样式按钮在后续大迁移中逐个替换。
 */

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger'
export type ButtonSize = 'sm' | 'md' | 'lg'

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: ButtonSize
}

export function Button({ variant = 'primary', size = 'md', type = 'button', className, ...rest }: ButtonProps) {
  const classes = ['btn', `btn-${variant}`, `btn-${size}`, className].filter(Boolean).join(' ')
  return <button type={type} className={classes} {...rest} />
}
