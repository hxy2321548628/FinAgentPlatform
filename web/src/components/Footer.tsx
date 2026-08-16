import { Link } from 'react-router-dom'
import { Logo } from './Logo'

export function Footer() {
  return (
    <footer style={{
      padding: '32px 80px', background: 'var(--bg)',
      borderTop: '1px solid var(--border)',
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    }}>
      <Link to="/" style={{ display: 'flex', alignItems: 'center', gap: 8, textDecoration: 'none' }}>
        <Logo height={20} />
        <span style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-primary)' }}>FinAgentPlatform</span>
      </Link>
      <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>© 2026 金融学院智能体平台</span>
      <div style={{ display: 'flex', gap: 24 }}>
        {[['智能体市场', '/marketplace'], ['研究范式', '/scenarios'], ['技术底座', '/capabilities'], ['数据要素', '/data']].map(([label, to]) => (
          <Link key={to} to={to} style={{ fontSize: 13, color: 'var(--text-secondary)', textDecoration: 'none' }}>
            {label}
          </Link>
        ))}
      </div>
    </footer>
  )
}
