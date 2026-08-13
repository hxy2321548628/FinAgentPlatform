import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { DecoStamp } from '../components/DecoStamp'
import { clearDemoAuth, loginDemoAdmin } from '../auth/demoAuth'

const LOGO_PATH_1 = 'M24.22,27.73l1.05-2c.36-.69.73-1.38,1.08-2.07a.26.26,0,0,1,.27-.17h3.83a.26.26,0,0,1,.27.18c1.44,3.06,3,6.08,4.65,9a.23.23,0,0,0,.08.16H27.09a.3.3,0,0,1-.32-.19q-1.2-2.34-2.42-4.66l-.14-.25c-.05.09-.1.16-.13.23l-2.44,4.7a.25.25,0,0,1-.26.17H13l.4-.83c1.53-2.72,2.94-5.5,4.27-8.33a.35.35,0,0,1,.38-.24h3.74a.27.27,0,0,1,.28.18l2,3.84Z'
const LOGO_PATH_2 = 'M24.21,4.19a82.908,82.908,0,0,0,2.43,9.16,85.1,85.1,0,0,0,3.43,8.85H18.33a79,79,0,0,0,3.47-8.86,84.311,84.311,0,0,0,2.41-9.15Zm0,16.18A1.3,1.3,0,1,0,23,19.07a1.26,1.26,0,0,0,1.23,1.3Z'

type Tab = 'login' | 'register'

export function Login() {
  const navigate = useNavigate()
  const [tab, setTab] = useState<Tab>('login')
  const [decoTime, setDecoTime] = useState('')
  const [loginName, setLoginName] = useState('')
  const [loginPassword, setLoginPassword] = useState('')
  const [loginBusy, setLoginBusy] = useState(false)
  const [loginError, setLoginError] = useState('')

  useEffect(() => {
    const update = () => {
      const now = new Date()
      const hh = String(now.getHours()).padStart(2, '0')
      const mm = String(now.getMinutes()).padStart(2, '0')
      setDecoTime(`ANALYSIS · ${hh}:${mm}`)
    }
    update()
    const id = setInterval(update, 60000)
    return () => clearInterval(id)
  }, [])

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    const name = loginName.trim()
    if (!name || !loginPassword) return
    setLoginBusy(true)
    setLoginError('')

    const tryDemoLogin = () => {
      if (!loginDemoAdmin(name, loginPassword)) {
        setLoginError('当前未连接后端，仅支持管理员演示账号登录')
        return
      }
      navigate('/admin', { replace: true })
    }

    try {
      const response = await fetch('/api/auth/login', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, password: loginPassword }),
      })
      if (!response.ok) {
        if (response.status === 404 || response.status >= 500) {
          tryDemoLogin()
          return
        }
        const body = await response.json().catch(() => null) as { error?: { message?: string } } | null
        setLoginError(body?.error?.message ?? '登录失败，请检查用户名和密码')
        return
      }

      const user = await response.json() as { role: string }
      clearDemoAuth()
      navigate(user.role === 'admin' ? '/admin' : '/workspace', { replace: true })
    } catch {
      tryDemoLogin()
    } finally {
      setLoginBusy(false)
    }
  }

  const handleRegister = (e: React.FormEvent) => {
    e.preventDefault()
    setTab('login')
  }

  return (
    <div style={{
      minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
      position: 'relative', overflow: 'hidden',
      backgroundColor: 'var(--bg)',
      backgroundImage: 'linear-gradient(rgba(11,46,92,0.035) 1px, transparent 1px), linear-gradient(90deg, rgba(11,46,92,0.035) 1px, transparent 1px)',
      backgroundSize: '40px 40px',
    }}>
      {/* 装饰时间戳 */}
      <DecoStamp style={{ position: 'fixed', top: 80, left: 80 }} text={decoTime} />
      <DecoStamp style={{ position: 'fixed', bottom: 80, right: 80 }} text={decoTime} />

      <div style={{
        display: 'flex', width: 900, minHeight: 540,
        background: 'var(--surface)', borderRadius: 16,
        border: '1px solid var(--border)',
        boxShadow: '0 4px 8px rgba(11,46,92,0.06), 0 20px 60px rgba(11,46,92,0.12)',
        overflow: 'hidden', position: 'relative', zIndex: 1,
      }}>

        {/* 左侧品牌区 */}
        <div style={{
          width: 380, flexShrink: 0,
          background: 'var(--brand)',
          backgroundImage: 'linear-gradient(rgba(255,255,255,0.04) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.04) 1px, transparent 1px)',
          backgroundSize: '40px 40px',
          display: 'flex', flexDirection: 'column', justifyContent: 'space-between',
          padding: '48px 44px', position: 'relative', overflow: 'hidden',
        }}>
          {/* 光晕装饰 */}
          <div style={{
            position: 'absolute', right: -60, top: -60,
            width: 300, height: 300, borderRadius: '50%',
            background: 'radial-gradient(circle, rgba(23,73,196,0.4) 0%, transparent 70%)',
            pointerEvents: 'none',
          }} />

          {/* Logo */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <svg viewBox="12 3 24 34" fill="currentColor" style={{ height: 32, width: 'auto', color: '#fff' }} aria-hidden="true">
              <path d={LOGO_PATH_1} /><path d={LOGO_PATH_2} />
            </svg>
            <span style={{ fontSize: 18, fontWeight: 700, color: '#fff', letterSpacing: '0.04em' }}>FinAgentPlatform</span>
          </div>

          {/* 品牌内容 */}
          <div style={{ marginTop: 60 }}>
            <div style={{ fontSize: 10, fontFamily: "'JetBrains Mono', monospace", textTransform: 'uppercase', letterSpacing: '0.3em', color: 'rgba(255,255,255,0.4)', marginBottom: 20 }}>
              // INTELLIGENCE MINIMAL
            </div>
            <div style={{ fontSize: 34, fontWeight: 900, color: '#fff', lineHeight: 1.2, marginBottom: 16 }}>
              金融学院<br />智能体平台
            </div>
            <div style={{ fontSize: 14, color: 'rgba(255,255,255,0.55)', lineHeight: 1.75 }}>
              提出分析问题，智能体自动编写代码、<br />
              在隔离沙箱中执行，返回结果与图表。
            </div>
          </div>

          {/* 右下角装饰 */}
          <div style={{
            position: 'absolute', bottom: 40, right: 30,
            fontSize: 11, fontFamily: "'JetBrains Mono', monospace",
            letterSpacing: '0.2em', color: 'rgba(255,255,255,0.1)',
            transform: 'rotate(-45deg)', whiteSpace: 'nowrap',
          }}>{decoTime}</div>
        </div>

        {/* 右侧表单区 */}
        <div style={{ flex: 1, padding: '60px 52px', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
          <div style={{ marginBottom: 36 }}>
            <div style={{ fontSize: 26, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 8 }}>
              {tab === 'login' ? '欢迎回来' : '创建账户'}
            </div>
            <div style={{ fontSize: 14, color: 'var(--text-secondary)' }}>
              {tab === 'login' ? '登录您的 FinAgentPlatform 账户' : '开始您的智能分析之旅'}
            </div>
          </div>

          {/* Tab 栏 */}
          <div style={{ display: 'flex', borderBottom: '1px solid var(--border)', marginBottom: 32 }}>
            {(['login', 'register'] as Tab[]).map(t => (
              <button key={t} onClick={() => setTab(t)} style={{
                padding: '10px 20px', fontSize: 14, fontWeight: 500, background: 'none', border: 'none',
                borderBottom: tab === t ? '2px solid var(--action)' : '2px solid transparent',
                marginBottom: -1, cursor: 'pointer', fontFamily: 'inherit',
                color: tab === t ? 'var(--action)' : 'var(--text-muted)',
                transition: 'color 0.2s, border-color 0.2s',
              }}>
                {t === 'login' ? '登录' : '注册'}
              </button>
            ))}
          </div>

          {/* 登录表单 */}
          {tab === 'login' && (
            <form onSubmit={handleLogin}>
              <Field label="用户名">
                <input className="login-input" type="text" autoComplete="username" placeholder="请输入用户名" value={loginName} onChange={event => setLoginName(event.target.value)}
                  style={inputStyle} />
              </Field>
              <Field label="密码">
                <input className="login-input" type="password" autoComplete="current-password" placeholder="请输入密码" value={loginPassword} onChange={event => setLoginPassword(event.target.value)}
                  style={inputStyle} />
              </Field>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: 'var(--text-secondary)', cursor: 'pointer' }}>
                  <input type="checkbox" defaultChecked style={{ accentColor: 'var(--action)' }} /> 记住我
                </label>
                <span style={{ fontSize: 13, color: 'var(--action)', cursor: 'pointer' }}>忘记密码？</span>
              </div>
              {loginError && <div role="alert" style={{ marginBottom: 16, padding: '9px 12px', border: '1px solid #FECACA', borderRadius: 6, background: '#FEF2F2', color: '#DC2626', fontSize: 13 }}>{loginError}</div>}
              <button type="submit" disabled={loginBusy || !loginName.trim() || !loginPassword} style={{ ...darkBtnStyle, opacity: loginBusy || !loginName.trim() || !loginPassword ? 0.6 : 1, cursor: loginBusy || !loginName.trim() || !loginPassword ? 'default' : 'pointer' }}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4M10 17l5-5-5-5M15 12H3"/>
                </svg>
                {loginBusy ? '正在登录…' : '登录系统'}
              </button>
              <div style={{ marginTop: 24, textAlign: 'center', fontSize: 13, color: 'var(--text-secondary)' }}>
                还没有账户？<span style={{ color: 'var(--action)', cursor: 'pointer', fontWeight: 500 }} onClick={() => setTab('register')}>立即注册</span>
              </div>
            </form>
          )}

          {/* 注册表单 */}
          {tab === 'register' && (
            <form onSubmit={handleRegister}>
              <Field label="用户名">
                <input type="text" placeholder="请输入用户名" style={inputStyle} />
              </Field>
              <Field label="邮箱地址">
                <input type="email" placeholder="your@company.com" style={inputStyle} />
              </Field>
              <Field label="密码">
                <input type="password" placeholder="至少 8 位字符" style={inputStyle} />
              </Field>
              <Field label="确认密码">
                <input type="password" placeholder="再次输入密码" style={inputStyle} />
              </Field>
              <button type="submit" style={darkBtnStyle}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/>
                  <line x1="19" y1="8" x2="19" y2="14"/><line x1="22" y1="11" x2="16" y2="11"/>
                </svg>
                创建账户
              </button>
              <div style={{ marginTop: 24, textAlign: 'center', fontSize: 13, color: 'var(--text-secondary)' }}>
                已有账户？<span style={{ color: 'var(--action)', cursor: 'pointer', fontWeight: 500 }} onClick={() => setTab('login')}>立即登录</span>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 20 }}>
      <label style={{ display: 'block', fontSize: 11, fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.15em', color: 'var(--text-muted)', marginBottom: 8 }}>
        {label}
      </label>
      {children}
    </div>
  )
}

const inputStyle: React.CSSProperties = {
  width: '100%', height: 40, border: '1px solid var(--border)', borderRadius: 6,
  padding: '0 12px', fontSize: 14, color: 'var(--text-primary)',
  background: '#F7F9FC', outline: 'none', fontFamily: 'inherit',
  boxSizing: 'border-box',
}

const darkBtnStyle: React.CSSProperties = {
  width: '100%', height: 44, background: 'var(--brand)', color: '#fff',
  border: 'none', borderRadius: 6, fontSize: 15, fontWeight: 600,
  cursor: 'pointer', letterSpacing: '0.03em', fontFamily: 'inherit',
  display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
  transition: 'background 0.15s',
}
