import * as DialogPrimitive from '@radix-ui/react-dialog'
import { useEffect, useState, type MouseEvent, type ReactNode } from 'react'
import { ChevronLeft, ChevronRight, X } from 'lucide-react'
import { Button } from '../../../components/ui/Button'
import { Skeleton } from '../../../components/ui/Skeleton'

interface AdminPageHeaderProps {
  eyebrow: string
  title: string
  description?: string
  pendingCount?: number
  pendingLabel?: string
  badgeText?: string
  actions?: ReactNode
}

export function AdminPageHeader({ eyebrow, title, description, pendingCount, pendingLabel = '个待审核', badgeText, actions }: AdminPageHeaderProps) {
  return (
    <header className="admin-page-header">
      <div className="admin-page-heading">
        <div className="admin-eyebrow">{eyebrow}</div>
        <h1 className="admin-page-title">{title}</h1>
        {description && <p className="admin-page-description">{description}</p>}
      </div>
      <div className="admin-page-header-actions">
        {pendingCount !== undefined && <span className="admin-pending-badge">{pendingCount} {pendingLabel}</span>}
        {pendingCount === undefined && badgeText && <span className="admin-pending-badge">{badgeText}</span>}
        {actions}
      </div>
    </header>
  )
}

interface AdminTableSectionProps {
  title: string
  action?: ReactNode
  children: ReactNode
}

export function AdminTableSection({ title, action, children }: AdminTableSectionProps) {
  return (
    <section className="admin-section">
      <header className="admin-section-header">
        <h2 className="admin-section-title">{title}</h2>
        {action}
      </header>
      <div className="admin-section-body">{children}</div>
    </section>
  )
}

export function AdminEmptyState({ title, description }: { title: string; description?: string }) {
  return (
    <div className="admin-empty">
      <strong>{title}</strong>
      {description && <span>{description}</span>}
    </div>
  )
}

export function AdminTableLoading({ label = '正在加载…' }: { label?: string }) {
  return (
    <div className="admin-table-loading" role="status">
      <span className="sr-only">{label}</span>
      {Array.from({ length: 4 }, (_, index) => <Skeleton key={index} height={44} radius={0} />)}
    </div>
  )
}

interface AdminViewOption<T extends string> {
  value: T
  label: string
  count: number
}

export function AdminViewTabs<T extends string>({ label, value, options, onChange }: {
  label: string
  value: T
  options: AdminViewOption<T>[]
  onChange: (value: T) => void
}) {
  return (
    <div className="admin-view-switcher">
      <div className="admin-filter-tabs" role="group" aria-label={label}>
        {options.map(option => (
          <button
            key={option.value}
            type="button"
            className={`admin-filter-tab${value === option.value ? ' active' : ''}`}
            aria-pressed={value === option.value}
            onClick={() => onChange(option.value)}
          >
            {option.label} <span>{option.count}</span>
          </button>
        ))}
      </div>
    </div>
  )
}

interface AdminPaginationProps {
  page: number
  pageSize: number
  totalItems: number
  itemName: string
  onPageChange: (page: number) => void
}

export function AdminPagination({ page, pageSize, totalItems, itemName, onPageChange }: AdminPaginationProps) {
  const totalPages = Math.max(1, Math.ceil(totalItems / pageSize))
  const safePage = Math.min(Math.max(page, 1), totalPages)
  const first = totalItems === 0 ? 0 : (safePage - 1) * pageSize + 1
  const last = Math.min(safePage * pageSize, totalItems)

  if (totalItems <= pageSize) return null

  const changePage = (nextPage: number, event: MouseEvent<HTMLButtonElement>) => {
    event.currentTarget.closest('.admin-section')?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
    onPageChange(nextPage)
  }

  return (
    <div className="admin-pagination">
      <span>显示 {first}–{last} 项，共 {totalItems} 个{itemName}</span>
      <nav aria-label={`${itemName}列表分页`}>
        <Button variant="secondary" size="sm" aria-label="上一页" disabled={safePage <= 1} onClick={event => changePage(safePage - 1, event)}>
          <ChevronLeft size={15} aria-hidden="true" />
          上一页
        </Button>
        <span className="admin-pagination-page" aria-live="polite">{safePage} / {totalPages}</span>
        <Button variant="secondary" size="sm" aria-label="下一页" disabled={safePage >= totalPages} onClick={event => changePage(safePage + 1, event)}>
          下一页
          <ChevronRight size={15} aria-hidden="true" />
        </Button>
      </nav>
    </div>
  )
}

export function AdminDetailDialog({ open, title, eyebrow, description, children, footer, onClose }: {
  open: boolean
  title: string
  eyebrow?: string
  description?: string
  children: ReactNode
  footer?: ReactNode
  onClose: () => void
}) {
  return (
    <DialogPrimitive.Root open={open} onOpenChange={value => {
      if (!value) onClose()
    }}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="dialog-overlay dialog-overlay-strong" />
        <DialogPrimitive.Content className="dialog-content admin-detail-dialog">
          <header className="admin-detail-dialog-header">
            <div>
              {eyebrow && <div className="admin-eyebrow">{eyebrow}</div>}
              <DialogPrimitive.Title className="admin-detail-dialog-title">{title}</DialogPrimitive.Title>
              <DialogPrimitive.Description className={description ? 'admin-detail-dialog-description' : 'sr-only'}>{description ?? '内容详情'}</DialogPrimitive.Description>
            </div>
            <DialogPrimitive.Close asChild>
              <button type="button" className="admin-detail-dialog-close" aria-label="关闭详情"><X size={17} aria-hidden="true" /></button>
            </DialogPrimitive.Close>
          </header>
          <div className="admin-detail-dialog-body">{children}</div>
          {footer && <footer className="admin-detail-dialog-footer">{footer}</footer>}
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  )
}

export function AdminListingDialog({ open, resourceName, enable, pending, error, disableDescription, enableDescription, onConfirm, onClose }: {
  open: boolean
  resourceName: string
  enable: boolean
  pending: boolean
  error?: string
  disableDescription?: string
  enableDescription?: string
  onConfirm: (reason?: string) => void
  onClose: () => void
}) {
  const [reason, setReason] = useState('')
  useEffect(() => {
    if (open) setReason('')
  }, [open, resourceName, enable])
  const disabling = !enable

  return (
    <DialogPrimitive.Root open={open} onOpenChange={value => {
      if (!value) onClose()
    }}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="dialog-overlay dialog-overlay-strong" />
        <DialogPrimitive.Content className="dialog-content admin-listing-dialog" aria-describedby={undefined}>
          <DialogPrimitive.Title className="dialog-title">{disabling ? `下架「${resourceName}」？` : `恢复上架「${resourceName}」？`}</DialogPrimitive.Title>
          <p className="dialog-desc">{disabling
            ? disableDescription ?? '下架后会立即从平台目录移除，但作者与已共享课题组仍可继续使用，历史运行不受影响。'
            : enableDescription ?? '恢复后会重新展示最近审核通过的版本。'}</p>
          {disabling && (
            <label className="admin-listing-reason">
              <span>下架原因 <strong>*</strong></span>
              <textarea value={reason} onChange={event => setReason(event.target.value)} maxLength={500} rows={4} placeholder="请写明下架原因，作者会看到这段说明" autoFocus />
              <small>{reason.length} / 500</small>
            </label>
          )}
          {error && <div role="alert" className="admin-inline-notice danger">{error}</div>}
          <div className="dialog-actions">
            <Button variant="secondary" size="sm" onClick={onClose} disabled={pending}>取消</Button>
            <Button variant={disabling ? 'danger' : 'primary'} size="sm" onClick={() => onConfirm(disabling ? reason.trim() : undefined)} disabled={pending || (disabling && !reason.trim())}>
              {pending ? '正在处理…' : disabling ? '确认下架' : '恢复上架'}
            </Button>
          </div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  )
}
