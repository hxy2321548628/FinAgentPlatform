import type { CSSProperties } from 'react'

export const pageStyle: CSSProperties = {
  flex: 1,
  minWidth: 0,
  width: '100%',
  overflowY: 'auto',
  overflowX: 'hidden',
  boxSizing: 'border-box',
  padding: '28px 32px',
  background: 'var(--bg)',
}

export const pageHeaderStyle: CSSProperties = {
  minHeight: 40,
  display: 'flex',
  alignItems: 'flex-start',
  justifyContent: 'space-between',
  gap: 20,
  marginBottom: 24,
}

export const eyebrowStyle: CSSProperties = {
  marginBottom: 4,
  color: 'var(--text-muted)',
  fontFamily: "'JetBrains Mono', monospace",
  fontSize: 10,
  letterSpacing: '0.3em',
  textTransform: 'uppercase',
}

export const pageTitleStyle: CSSProperties = {
  margin: 0,
  color: 'var(--text-primary)',
  fontSize: 22,
  fontWeight: 700,
  lineHeight: 1.25,
}

export const pendingBadgeStyle: CSSProperties = {
  padding: '5px 12px',
  border: '1px solid var(--action-border)',
  borderRadius: 20,
  background: 'var(--action-light)',
  color: 'var(--action)',
  fontSize: 12,
  fontWeight: 700,
  whiteSpace: 'nowrap',
}

export const sectionStyle: CSSProperties = {
  marginBottom: 24,
  overflow: 'hidden',
  border: '1px solid var(--border)',
  borderRadius: 10,
  background: 'var(--surface)',
}

export const sectionHeaderStyle: CSSProperties = {
  padding: '13px 18px',
  borderBottom: '1px solid var(--border)',
  color: 'var(--text-primary)',
  fontSize: 13,
  fontWeight: 700,
}

export const tableStyle: CSSProperties = {
  width: '100%',
  borderCollapse: 'collapse',
  fontSize: 13,
}

export const thStyle: CSSProperties = {
  padding: '10px 16px',
  borderBottom: '1px solid var(--border)',
  background: 'var(--bg)',
  color: 'var(--text-muted)',
  fontSize: 11,
  fontWeight: 600,
  letterSpacing: '0.08em',
  textAlign: 'left',
  textTransform: 'uppercase',
  whiteSpace: 'nowrap',
}

export const cellStyle: CSSProperties = {
  padding: '12px 16px',
  color: 'var(--text-secondary)',
  verticalAlign: 'middle',
}

export const nameCellStyle: CSSProperties = {
  ...cellStyle,
  minWidth: 180,
  color: 'var(--text-primary)',
  fontWeight: 600,
}

export const monoCellStyle: CSSProperties = {
  ...cellStyle,
  color: 'var(--text-muted)',
  fontFamily: "'JetBrains Mono', monospace",
  fontSize: 12,
  whiteSpace: 'nowrap',
}

export const tagStyle: CSSProperties = {
  display: 'inline-block',
  padding: '2px 7px',
  border: '1px solid var(--action-border)',
  borderRadius: 4,
  background: 'var(--action-light)',
  color: 'var(--action)',
  fontSize: 11,
  whiteSpace: 'nowrap',
}

export const approveButtonStyle: CSSProperties = {
  padding: '6px 12px',
  border: 'none',
  borderRadius: 6,
  background: 'var(--action)',
  color: '#fff',
  cursor: 'pointer',
  fontFamily: 'inherit',
  fontSize: 12,
  fontWeight: 600,
  whiteSpace: 'nowrap',
}

export const rejectButtonStyle: CSSProperties = {
  ...approveButtonStyle,
  background: '#DC2626',
}

export const secondaryButtonStyle: CSSProperties = {
  padding: '6px 12px',
  border: '1px solid var(--border)',
  borderRadius: 6,
  background: 'var(--surface)',
  color: 'var(--text-secondary)',
  cursor: 'pointer',
  fontFamily: 'inherit',
  fontSize: 12,
  whiteSpace: 'nowrap',
}

export const emptyStyle: CSSProperties = {
  padding: '48px 20px',
  color: 'var(--text-muted)',
  fontSize: 13,
  textAlign: 'center',
}
