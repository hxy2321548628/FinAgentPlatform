import type { ReactNode } from 'react'
import {
  eyebrowStyle,
  pageHeaderStyle,
  pageTitleStyle,
  pendingBadgeStyle,
  sectionHeaderStyle,
  sectionStyle,
} from './AdminStyles'

interface AdminPageHeaderProps {
  eyebrow: string
  title: string
  description?: string
  pendingCount?: number
  pendingLabel?: string
  badgeText?: string
}

export function AdminPageHeader({ eyebrow, title, description, pendingCount, pendingLabel = '个待审核', badgeText }: AdminPageHeaderProps) {
  return (
    <div style={pageHeaderStyle}>
      <div>
        <div style={eyebrowStyle}>{eyebrow}</div>
        <h1 style={pageTitleStyle}>{title}</h1>
        {description && <p style={{ maxWidth: 760, marginTop: 6, color: 'var(--text-muted)', fontSize: 13, lineHeight: 1.7 }}>{description}</p>}
      </div>
      {pendingCount !== undefined && <span style={pendingBadgeStyle}>{pendingCount} {pendingLabel}</span>}
      {pendingCount === undefined && badgeText && <span style={pendingBadgeStyle}>{badgeText}</span>}
    </div>
  )
}

interface AdminTableSectionProps {
  title: string
  action?: ReactNode
  children: ReactNode
}

export function AdminTableSection({ title, action, children }: AdminTableSectionProps) {
  return (
    <section style={sectionStyle}>
      <div style={{ ...sectionHeaderStyle, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16 }}>
        <span>{title}</span>
        {action}
      </div>
      <div className="admin-section-body">{children}</div>
    </section>
  )
}
