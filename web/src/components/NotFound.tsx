import { Link } from 'react-router-dom'

interface NotFoundProps {
  title?: string
  description?: string
  primaryTo: string
  primaryLabel: string
  secondaryTo?: string
  secondaryLabel?: string
}

export function NotFound({
  title = '页面不存在',
  description = '您访问的地址不存在，或页面已经被移动。',
  primaryTo,
  primaryLabel,
  secondaryTo,
  secondaryLabel,
}: NotFoundProps) {
  return (
    <div className="grid-bg" style={{ flex: 1, minHeight: 0, display: 'grid', placeItems: 'center', padding: 40, overflow: 'auto' }}>
      <div style={{ width: '100%', maxWidth: 560, textAlign: 'center' }}>
        <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 96, fontWeight: 800, lineHeight: 1, color: 'var(--action)', opacity: 0.16 }}>404</div>
        <div className="section-tag" style={{ marginTop: -8 }}>// PAGE NOT FOUND</div>
        <h1 style={{ margin: '14px 0 10px', fontSize: 30, color: 'var(--text-primary)' }}>{title}</h1>
        <p style={{ margin: '0 auto', maxWidth: 440, fontSize: 14, lineHeight: 1.8, color: 'var(--text-secondary)' }}>{description}</p>
        <div style={{ display: 'flex', justifyContent: 'center', gap: 12, marginTop: 28, flexWrap: 'wrap' }}>
          <Link to={primaryTo} style={primaryLinkStyle}>{primaryLabel}</Link>
          {secondaryTo && secondaryLabel && <Link to={secondaryTo} style={secondaryLinkStyle}>{secondaryLabel}</Link>}
        </div>
      </div>
    </div>
  )
}

const primaryLinkStyle: React.CSSProperties = {
  display: 'inline-flex', alignItems: 'center', justifyContent: 'center', height: 40,
  padding: '0 20px', borderRadius: 7, background: 'var(--action)', color: '#fff',
  textDecoration: 'none', fontSize: 13, fontWeight: 600,
}

const secondaryLinkStyle: React.CSSProperties = {
  ...primaryLinkStyle,
  background: 'var(--surface)', color: 'var(--text-secondary)', border: '1px solid var(--border)',
}
