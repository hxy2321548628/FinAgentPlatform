import { useState } from 'react'

export interface CatalogFilter {
  key: string
  label: string
}

interface CatalogControlsProps {
  search: string
  onSearch: (value: string) => void
  placeholder: string
  filters: CatalogFilter[]
  activeFilter: string
  onFilter: (key: string) => void
  sortLabel?: string | null
}

export function CatalogControls({ search, onSearch, placeholder, filters, activeFilter, onFilter, sortLabel = '调用次数' }: CatalogControlsProps) {
  return (
    <>
      <div style={{ padding: '16px 36px', display: 'flex', alignItems: 'center', gap: 12 }}>
        <div style={{ flex: 1, position: 'relative', maxWidth: 320 }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)', pointerEvents: 'none' }}>
            <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
          </svg>
          <input
            value={search}
            onChange={event => onSearch(event.target.value)}
            placeholder={placeholder}
            style={{ width: '100%', height: 36, padding: '0 12px 0 32px', border: '1px solid var(--border)', borderRadius: 7, fontSize: 13, fontFamily: 'inherit', outline: 'none', background: 'var(--surface)', color: 'var(--text-primary)', boxSizing: 'border-box', transition: 'border-color 0.15s' }}
            onFocus={event => (event.target.style.borderColor = 'var(--action)')}
            onBlur={event => (event.target.style.borderColor = 'var(--border)')}
          />
          {search && (
            <button type="button" aria-label="清除搜索" onClick={() => onSearch('')} style={{ position: 'absolute', right: 8, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', fontSize: 14, lineHeight: 1 }}>×</button>
          )}
        </div>
        {sortLabel && (
          <div style={{ marginLeft: 'auto', display: 'flex', gap: 6, alignItems: 'center' }}>
            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>排序：</span>
            <span style={{ padding: '5px 12px', borderRadius: 6, border: '1px solid var(--action-border)', background: 'var(--action-light)', color: 'var(--action)', fontSize: 12 }}>{sortLabel}</span>
          </div>
        )}
      </div>
      <div style={{ padding: '0 36px 20px', display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        {filters.map(({ key, label }) => (
          <button
            type="button"
            key={key}
            onClick={() => onFilter(key)}
            style={{
              padding: '6px 16px', borderRadius: 6,
              border: '1px solid ' + (activeFilter === key ? 'var(--action)' : 'var(--border)'),
              background: activeFilter === key ? 'var(--action)' : 'var(--surface)',
              color: activeFilter === key ? '#fff' : 'var(--text-secondary)',
              fontSize: 12, fontWeight: activeFilter === key ? 600 : 400,
              cursor: 'pointer', fontFamily: 'inherit', transition: 'all 0.15s',
            }}
          >{label}</button>
        ))}
      </div>
    </>
  )
}

interface CatalogAction {
  label: string
  onClick: () => void
}

interface CatalogCardProps {
  title: string
  version?: string
  author: string
  subject: string
  description: string
  detail: string
  badges?: string[]
  metric: string
  secondaryAction?: CatalogAction
  primaryAction?: CatalogAction
}

export function CatalogCard({ title, version, author, subject, description, detail, badges = [], metric, secondaryAction, primaryAction }: CatalogCardProps) {
  const [hovered, setHovered] = useState(false)

  return (
    <article
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{ background: 'var(--surface)', border: '1px solid ' + (hovered ? 'var(--action-border)' : 'var(--border)'), borderRadius: 10, padding: 24, display: 'flex', flexDirection: 'column', gap: 10, boxShadow: hovered ? '0 4px 16px rgba(23,73,196,0.08)' : 'none', transition: 'border-color 0.2s, box-shadow 0.2s' }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
        <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: 6 }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" style={{ color: 'var(--action)', flexShrink: 0 }}><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M9 21V9"/></svg>
          {title}
        </div>
        {version && <span style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: "'JetBrains Mono', monospace", flexShrink: 0, marginLeft: 8 }}>{version}</span>}
      </div>
      <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{author} · {subject}</div>
      <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.65, flex: 1 }}>{description}</p>
      {badges.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {badges.map(badge => <span key={badge} style={{ padding: '2px 8px', fontSize: 11, fontWeight: 500, color: 'var(--text-secondary)', border: '1px solid var(--border)', borderRadius: 3 }}>{badge}</span>)}
        </div>
      )}
      <div style={{ fontSize: 12, color: 'var(--text-muted)', padding: '8px 0', borderTop: '1px solid var(--border-light)', borderBottom: '1px solid var(--border-light)' }}>{detail}</div>
      <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>▶ {metric}</div>
      {(secondaryAction || primaryAction) && (
        <div style={{ display: 'flex', gap: 8 }}>
          {secondaryAction && <button type="button" onClick={secondaryAction.onClick} style={{ flex: 1, padding: '7px 0', background: 'transparent', color: 'var(--action)', border: '1px solid var(--action-border)', borderRadius: 7, fontSize: 13, cursor: 'pointer', fontFamily: 'inherit' }}>{secondaryAction.label}</button>}
          {primaryAction && <button type="button" onClick={primaryAction.onClick} style={{ flex: 1, padding: '7px 0', background: 'var(--action)', color: '#fff', border: 'none', borderRadius: 7, fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>{primaryAction.label}</button>}
        </div>
      )}
    </article>
  )
}
