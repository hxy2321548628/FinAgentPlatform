import { createContext, useContext } from 'react'

/** toast 输入与 hook（独立文件：Fast Refresh 只容忍组件独占的文件导出）。 */

export type ToastVariant = 'default' | 'success' | 'error'

export interface ToastInput {
  title: string
  description?: string
  variant?: ToastVariant
}

export interface ToastItem extends ToastInput {
  id: number
}

export const ToastContext = createContext<{ toast: (input: ToastInput) => void } | null>(null)

export function useToast(): { toast: (input: ToastInput) => void } {
  const context = useContext(ToastContext)
  if (!context) throw new Error('useToast 必须在 ToastProvider 内使用')
  return context
}
