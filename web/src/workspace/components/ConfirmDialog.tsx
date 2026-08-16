import * as AlertDialog from '@radix-ui/react-alert-dialog'
import { Button } from '../../components/ui/Button'

/**
 * 危险操作确认弹窗（DSD 第二章 §2.7/§2.8）。
 *
 * P1 b1 起改用 Radix AlertDialog：焦点陷阱、Esc 关闭、`role="alertdialog"` 语义
 * 全部由 Radix 承担，不再手写。接口与旧版一致，调用方无需改动。
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
  return (
    <AlertDialog.Root open={open} onOpenChange={value => {
      if (!value) onCancel()
    }}>
      <AlertDialog.Portal>
        <AlertDialog.Overlay className="dialog-overlay" onClick={onCancel} />
        <AlertDialog.Content className="dialog-content" aria-describedby={undefined}>
          <AlertDialog.Title className="dialog-title">{title}</AlertDialog.Title>
          {message && <AlertDialog.Description className="dialog-desc">{message}</AlertDialog.Description>}
          <div className="dialog-actions">
            <AlertDialog.Cancel asChild>
              <Button variant="secondary" size="sm">{cancelLabel}</Button>
            </AlertDialog.Cancel>
            <Button variant={danger ? 'danger' : 'primary'} size="sm" onClick={onConfirm}>{confirmLabel}</Button>
          </div>
        </AlertDialog.Content>
      </AlertDialog.Portal>
    </AlertDialog.Root>
  )
}
