import { useCallback, useRef, useState } from 'react'
import * as RadixToast from '@radix-ui/react-toast'
import { ToastContext, type ToastInput, type ToastItem } from './toast-context'

/**
 * 轻量 toast（DSD 第二章 §2.4）：右上角、3s 自动消失、三态，aria-live 由
 * Radix 语义承载。替换散落各页的内联通知小字。
 *
 * 用法：
 *   const { toast } = useToast()
 *   toast({ title: '文件已保存' })
 *   toast({ title: '保存失败', description: '请重试', variant: 'error' })
 */

let nextId = 1

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([])
  const timers = useRef(new Map<number, ReturnType<typeof setTimeout>>())

  const toast = useCallback((input: ToastInput) => {
    const id = nextId++
    setItems(current => [...current.slice(-2), { ...input, id }])
    // 兜底超时移除：Radix duration 到期会触发 onOpenChange(false)，
    // 这里再保一道，避免异常路径下 toast 残留
    const timer = setTimeout(() => {
      setItems(current => current.filter(one => one.id !== id))
      timers.current.delete(id)
    }, 4000)
    timers.current.set(id, timer)
  }, [])

  const remove = (id: number) => {
    const timer = timers.current.get(id)
    if (timer) {
      clearTimeout(timer)
      timers.current.delete(id)
    }
    setItems(current => current.filter(one => one.id !== id))
  }

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      <RadixToast.Provider duration={3000}>
        {items.map(item => (
          <RadixToast.Root key={item.id} className={`toast toast-${item.variant ?? 'default'}`} onOpenChange={open => {
            if (!open) remove(item.id)
          }}>
            <RadixToast.Title className="toast-title">{item.title}</RadixToast.Title>
            {item.description && <RadixToast.Description className="toast-desc">{item.description}</RadixToast.Description>}
            <RadixToast.Close className="toast-close" aria-label="关闭通知">×</RadixToast.Close>
          </RadixToast.Root>
        ))}
        <RadixToast.Viewport className="toast-viewport" aria-label="通知" />
      </RadixToast.Provider>
    </ToastContext.Provider>
  )
}
