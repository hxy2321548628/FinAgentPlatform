import { useEffect, useRef } from 'react'

/**
 * 危险操作确认弹窗（DSD 第二章 §2.7/§2.8）。
 *
 * 替代 window.confirm：Esc 关闭、遮罩点击关闭、Tab 焦点圈在面板内、
 * 初始焦点落在「取消」（安全选项）。语义用 `role="alertdialog"`。
 * P1 引入 Radix 后此组件可整体换掉，接口保持不变。
 */

interface ConfirmDialogProps {
  open: boolean
  title: string
  message?: string
  confirmLabel?: string
  cancelLabel?: string
  /** 危险操作用 --danger 底，普通确认用 --action。 */
  danger?: boolean
  onConfirm: () => void
  onCancel: () => void
}

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = '确认',
  cancelLabel = '取消',
  danger = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const panelRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    panelRef.current?.querySelector<HTMLButtonElement>('[data-confirm-cancel]')?.focus()
  }, [open])

  if (!open) return null

  const handleKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === 'Escape') {
      event.preventDefault()
      onCancel()
      return
    }
    if (event.key !== 'Tab') return
    const panel = panelRef.current
    if (!panel) return
    const focusables = Array.from(panel.querySelectorAll<HTMLElement>('button:not([disabled])'))
    if (focusables.length === 0) return
    const first = focusables[0]
    const last = focusables[focusables.length - 1]
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault()
      last.focus()
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault()
      first.focus()
    }
  }

  return (
    <div role="presentation" onClick={onCancel} style={{ position: 'fixed', inset: 0, zIndex: 400, display: 'grid', placeItems: 'center', padding: 20, background: 'rgba(11,46,92,0.25)', overscrollBehavior: 'contain' }}>
      <div
        ref={panelRef}
        role="alertdialog"
        aria-modal="true"
        aria-label={title}
        onClick={event => event.stopPropagation()}
        onKeyDown={handleKeyDown}
        style={{ width: 'min(420px, 100%)', padding: 20, borderRadius: 10, background: 'var(--surface)', boxShadow: '0 16px 45px rgba(11,46,92,0.2)' }}
      >
        <div style={{ marginBottom: 8, fontSize: 15, fontWeight: 700, color: 'var(--text-primary)' }}>{title}</div>
        {message && <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.7, overflowWrap: 'anywhere' }}>{message}</div>}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 18 }}>
          <button type="button" data-confirm-cancel onClick={onCancel} style={{ padding: '8px 16px', border: '1px solid var(--border)', borderRadius: 6, background: 'var(--surface)', color: 'var(--text-secondary)', cursor: 'pointer', fontFamily: 'inherit', fontSize: 13 }}>{cancelLabel}</button>
          <button type="button" onClick={onConfirm} style={{ padding: '8px 16px', border: 'none', borderRadius: 6, background: danger ? 'var(--danger)' : 'var(--action)', color: '#fff', cursor: 'pointer', fontFamily: 'inherit', fontSize: 13, fontWeight: 600 }}>{confirmLabel}</button>
        </div>
      </div>
    </div>
  )
}
