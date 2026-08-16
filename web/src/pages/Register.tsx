import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import { register } from '../api/auth'
import { errorMessage } from '../api/request'

export function Register() {
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [dept, setDept] = useState('')
  const [inviteCode, setInviteCode] = useState('')
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const mutation = useMutation({
    mutationFn: () => register(name.trim(), email.trim(), password, inviteCode, dept),
    onSuccess(result) {
      setError('')
      setSuccess(result.is_active
        ? `注册成功，已加入${result.group_name ? `「${result.group_name}」` : '对应课题组'}，现在可以登录。`
        : '注册申请已提交，请等待管理员审批后再登录。')
    },
    onError(reason) {
      setSuccess('')
      setError(errorMessage(reason, '注册失败，请稍后重试'))
    },
  })

  // 邮箱是登录凭据，后端非空且唯一 —— 这里先挡一道，省掉一次 422 往返
  const ready = Boolean(name.trim()) && /^[^@\s]+@[^@\s]+$/.test(email.trim()) && password.length >= 8

  const submit = (event: React.FormEvent) => {
    event.preventDefault()
    if (!ready) return
    setError('')
    setSuccess('')
    mutation.mutate()
  }

  return (
    <div style={pageStyle}>
      <div style={cardStyle}>
        <div style={brandStyle}>
          <div style={{ fontSize: 11, letterSpacing: '0.22em', color: 'rgba(255,255,255,0.55)', fontFamily: "'JetBrains Mono', monospace" }}>FINAGENTPLATFORM</div>
          <div style={{ marginTop: 42, fontSize: 32, lineHeight: 1.25, fontWeight: 800, color: '#fff' }}>加入金融学院<br />智能体平台</div>
          <p style={{ marginTop: 18, color: 'rgba(255,255,255,0.62)', lineHeight: 1.7, fontSize: 13 }}>注册后即可申请使用平台。没有邀请码的账号需要管理员审批。</p>
        </div>
        <div style={formPanelStyle}>
          <div style={{ marginBottom: 28 }}>
            <h1 style={{ margin: 0, fontSize: 26, color: 'var(--text-primary)' }}>创建账号</h1>
            <p style={{ margin: '8px 0 0', color: 'var(--text-secondary)', fontSize: 14 }}>注册账号后等待平台开通访问权限</p>
          </div>
          <form onSubmit={submit}>
            <Field label="用户名" id="reg-name"><input autoFocus id="reg-name" name="username" autoComplete="username" placeholder="请输入用户名" value={name} onChange={event => setName(event.target.value)} style={inputStyle} /></Field>
            <Field label="邮箱" id="reg-email"><input id="reg-email" name="email" type="email" autoComplete="email" placeholder="用它也能登录" value={email} onChange={event => setEmail(event.target.value)} style={inputStyle} /></Field>
            <Field label="密码" id="reg-password"><input id="reg-password" name="password" type="password" autoComplete="new-password" placeholder="至少 8 位密码" value={password} onChange={event => setPassword(event.target.value)} style={inputStyle} /></Field>
            <Field label="院系（可选）" id="reg-dept"><input id="reg-dept" name="department" autoComplete="organization" placeholder="如：金融学院" value={dept} onChange={event => setDept(event.target.value)} style={inputStyle} /></Field>
            <Field label="邀请码（可选）" id="reg-invite"><input id="reg-invite" name="invite_code" autoComplete="off" placeholder="有邀请码可直接加入课题组" value={inviteCode} onChange={event => setInviteCode(event.target.value)} style={inputStyle} /></Field>
            {error && <div role="alert" style={alertStyle}>{error}</div>}
            {success && <div role="status" style={successStyle}>{success}</div>}
            <button type="submit" disabled={mutation.isPending || !ready} style={{ ...buttonStyle, opacity: mutation.isPending || !ready ? 0.6 : 1 }}>{mutation.isPending ? '正在提交…' : '提交注册申请'}</button>
          </form>
          <div style={{ marginTop: 20, textAlign: 'center', fontSize: 13, color: 'var(--text-secondary)' }}>已有账号？ <Link to="/login" style={{ color: 'var(--action)', fontWeight: 600 }}>返回登录</Link></div>
        </div>
      </div>
      <button type="button" onClick={() => navigate('/login')} style={{ position: 'fixed', top: 24, right: 28, border: 'none', background: 'transparent', color: 'var(--text-secondary)', cursor: 'pointer', fontFamily: 'inherit' }}>← 登录</button>
    </div>
  )
}

function Field({ label, id, children }: { label: string; id: string; children: React.ReactNode }) {
  return <div style={{ marginBottom: 18 }}><label htmlFor={id} style={{ display: 'block', marginBottom: 7, fontSize: 11, letterSpacing: '0.14em', color: 'var(--text-muted)' }}>{label}</label>{children}</div>
}

const pageStyle: React.CSSProperties = { minHeight: '100vh', display: 'grid', placeItems: 'center', padding: 24, background: 'var(--bg)' }
const cardStyle: React.CSSProperties = { display: 'flex', width: 'min(900px, 100%)', minHeight: 540, overflow: 'hidden', border: '1px solid var(--border)', borderRadius: 16, background: 'var(--surface)', boxShadow: '0 20px 60px rgba(11,46,92,0.12)' }
const brandStyle: React.CSSProperties = { width: 340, flexShrink: 0, padding: '48px 40px', background: 'var(--brand)', backgroundImage: 'linear-gradient(rgba(255,255,255,0.04) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.04) 1px, transparent 1px)', backgroundSize: '40px 40px' }
const formPanelStyle: React.CSSProperties = { flex: 1, padding: '58px 52px', display: 'flex', flexDirection: 'column', justifyContent: 'center' }
const inputStyle: React.CSSProperties = { width: '100%', height: 40, boxSizing: 'border-box', border: '1px solid var(--border)', borderRadius: 6, padding: '0 12px', fontSize: 14, color: 'var(--text-primary)', background: 'var(--input-bg)', fontFamily: 'inherit' }
const buttonStyle: React.CSSProperties = { width: '100%', height: 44, border: 'none', borderRadius: 6, background: 'var(--brand)', color: '#fff', fontSize: 15, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }
const alertStyle: React.CSSProperties = { marginBottom: 14, padding: '9px 12px', border: '1px solid #FECACA', borderRadius: 6, background: 'var(--danger-bg)', color: 'var(--danger)', fontSize: 13 }
const successStyle: React.CSSProperties = { marginBottom: 14, padding: '9px 12px', border: '1px solid #BBF7D0', borderRadius: 6, background: 'var(--success-bg)', color: 'var(--success)', fontSize: 13, lineHeight: 1.6 }
