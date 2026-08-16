import { useState, useEffect } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import { DecoStamp } from '../components/DecoStamp'
import { AUTH_QUERY_KEY, login } from '../api/auth'
import { errorMessage } from '../api/request'
import { Logo } from '../components/Logo'

export function Login() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [decoTime, setDecoTime] = useState('')
  const [loginName, setLoginName] = useState('')
  const [loginPassword, setLoginPassword] = useState('')
  const [loginError, setLoginError] = useState('')
  const loginMutation = useMutation({
    mutationFn: ({ name, password }: { name: string; password: string }) => login(name, password),
    onSuccess(user) {
      // /login 可在同一个 SPA 会话中直接访问。先清掉前一账号的 threads/runs/files
      // 缓存，避免新账号短暂看到 staleTime 内仍属“新鲜”的旧数据。
      queryClient.clear()
      queryClient.setQueryData(AUTH_QUERY_KEY, user)
      // **reviewer 也进后台。** 它登进来就是为了清审核队列，落在工作台的话
      // 还得自己找路 —— 而工作台里原本一个后台入口都没有。`/admin` 会按角色分流
      const backend = user.role === 'admin' || user.role === 'reviewer'
      navigate(backend ? '/admin' : '/workspace', { replace: true })
    },
    onError(error) {
      setLoginError(errorMessage(error, '登录失败，请检查账号和密码'))
    },
  })

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
    setLoginError('')
    loginMutation.mutate({ name, password: loginPassword })
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
            <Logo height={32} color="#fff" />
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
              欢迎回来
            </div>
            <div style={{ fontSize: 14, color: 'var(--text-secondary)' }}>
              登录您的 FinAgentPlatform 账户
            </div>
          </div>

          {/* 登录表单 */}
          <form onSubmit={handleLogin}>
            <Field label="用户名或邮箱" id="login-name">
              <input className="login-input" id="login-name" name="username" type="text" autoComplete="username" placeholder="用户名或邮箱都可以" value={loginName} onChange={event => setLoginName(event.target.value)}
                style={inputStyle} />
            </Field>
            <Field label="密码" id="login-password">
              <input className="login-input" id="login-password" name="password" type="password" autoComplete="current-password" placeholder="请输入密码" value={loginPassword} onChange={event => setLoginPassword(event.target.value)}
                style={inputStyle} />
            </Field>
            {loginError && <div role="alert" style={{ marginBottom: 16, padding: '9px 12px', border: '1px solid #FECACA', borderRadius: 6, background: 'var(--danger-bg)', color: 'var(--danger)', fontSize: 13 }}>{loginError}</div>}
            <button type="submit" disabled={loginMutation.isPending || !loginName.trim() || !loginPassword} style={{ ...darkBtnStyle, opacity: loginMutation.isPending || !loginName.trim() || !loginPassword ? 0.6 : 1, cursor: loginMutation.isPending || !loginName.trim() || !loginPassword ? 'default' : 'pointer' }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4M10 17l5-5-5-5M15 12H3"/>
              </svg>
              {loginMutation.isPending ? '正在登录…' : '登录系统'}
            </button>
          </form>
          <div style={{ marginTop: 20, textAlign: 'center', fontSize: 13, color: 'var(--text-secondary)' }}>还没有账号？ <Link to="/register" style={{ color: 'var(--action)', fontWeight: 600 }}>注册账号</Link></div>
        </div>
      </div>
    </div>
  )
}

function Field({ label, id, children }: { label: string; id: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 20 }}>
      <label htmlFor={id} style={{ display: 'block', fontSize: 11, fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.15em', color: 'var(--text-muted)', marginBottom: 8 }}>
        {label}
      </label>
      {children}
    </div>
  )
}

const inputStyle: React.CSSProperties = {
  width: '100%', height: 40, border: '1px solid var(--border)', borderRadius: 6,
  padding: '0 12px', fontSize: 14, color: 'var(--text-primary)',
  background: 'var(--input-bg)', fontFamily: 'inherit',
  boxSizing: 'border-box',
}

const darkBtnStyle: React.CSSProperties = {
  width: '100%', height: 44, background: 'var(--brand)', color: '#fff',
  border: 'none', borderRadius: 6, fontSize: 15, fontWeight: 600,
  cursor: 'pointer', letterSpacing: '0.03em', fontFamily: 'inherit',
  display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
  transition: 'background 0.15s',
}
