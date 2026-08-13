import { useEffect, useState } from 'react'

interface PublishDialogProps {
  kindLabel: string
  initialName: string
  initialDescription: string
  existingNames: string[]
  onClose: () => void
  onSubmit: (name: string, description: string) => void
}

export function PublishDialog({ kindLabel, initialName, initialDescription, existingNames, onClose, onSubmit }: PublishDialogProps) {
  const [name, setName] = useState(initialName)
  const [description, setDescription] = useState(initialDescription)

  useEffect(() => {
    setName(initialName)
    setDescription(initialDescription)
  }, [initialDescription, initialName])

  const normalizedName = name.trim()
  const duplicate = existingNames.some(existing => existing.trim().toLocaleLowerCase('zh-CN') === normalizedName.toLocaleLowerCase('zh-CN'))
  const ready = Boolean(normalizedName && description.trim() && !duplicate)

  const submit = (event: React.FormEvent) => {
    event.preventDefault()
    if (!ready) return
    onSubmit(normalizedName, description.trim())
  }

  return (
    <>
      <div onClick={onClose} style={backdropStyle} />
      <div role="dialog" aria-modal="true" aria-label={`发布${kindLabel}`} style={modalStyle}>
        <div style={headerStyle}>
          <div>
            <div style={{ fontSize: 17, fontWeight: 700, color: 'var(--text-primary)' }}>发布{kindLabel}</div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>公开名称需全库唯一，提交后进入审核，不会离开当前页面。</div>
          </div>
          <button type="button" onClick={onClose} aria-label="关闭" style={closeStyle}>×</button>
        </div>
        <form onSubmit={submit}>
          <div style={{ marginBottom: 16 }}>
            <label style={labelStyle}>公开名称 <span style={{ color: '#DC2626' }}>*</span></label>
            <input value={name} onChange={event => setName(event.target.value)} placeholder={`请输入${kindLabel}公开名称`} style={{ ...inputStyle, borderColor: duplicate ? '#DC2626' : 'var(--border)' }} />
            {duplicate && <div style={{ fontSize: 12, color: '#DC2626', marginTop: 6 }}>该名称已被使用，请换一个公开名称。</div>}
          </div>
          <div style={{ marginBottom: 20 }}>
            <label style={labelStyle}>公开描述 <span style={{ color: '#DC2626' }}>*</span></label>
            <textarea value={description} onChange={event => setDescription(event.target.value)} placeholder={`说明${kindLabel}解决的问题、适用范围和主要输出`} style={{ ...inputStyle, minHeight: 110, resize: 'vertical' }} />
          </div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
            <button type="button" onClick={onClose} style={secondaryButtonStyle}>取消</button>
            <button type="submit" disabled={!ready} style={{ ...primaryButtonStyle, background: ready ? 'var(--action)' : 'var(--text-muted)', cursor: ready ? 'pointer' : 'default' }}>提交审核</button>
          </div>
        </form>
      </div>
    </>
  )
}

const backdropStyle: React.CSSProperties = { position: 'fixed', inset: 0, background: 'rgba(13,24,41,0.4)', backdropFilter: 'blur(4px)', zIndex: 300 }
const modalStyle: React.CSSProperties = { position: 'fixed', top: '50%', left: '50%', transform: 'translate(-50%,-50%)', width: 520, maxWidth: 'calc(100vw - 40px)', padding: 30, background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12, boxShadow: '0 20px 60px rgba(11,46,92,0.2)', zIndex: 301 }
const headerStyle: React.CSSProperties = { display: 'flex', justifyContent: 'space-between', gap: 16, alignItems: 'flex-start', marginBottom: 22 }
const closeStyle: React.CSSProperties = { border: 'none', background: 'none', color: 'var(--text-muted)', fontSize: 20, cursor: 'pointer' }
const labelStyle: React.CSSProperties = { display: 'block', fontSize: 13, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 6 }
const inputStyle: React.CSSProperties = { width: '100%', boxSizing: 'border-box', padding: '9px 12px', border: '1px solid var(--border)', borderRadius: 7, background: 'var(--surface)', color: 'var(--text-primary)', fontSize: 13, fontFamily: 'inherit', outline: 'none' }
const primaryButtonStyle: React.CSSProperties = { padding: '9px 20px', color: '#fff', border: 'none', borderRadius: 7, fontSize: 13, fontWeight: 600, fontFamily: 'inherit' }
const secondaryButtonStyle: React.CSSProperties = { padding: '9px 18px', background: 'transparent', color: 'var(--text-secondary)', border: '1px solid var(--border)', borderRadius: 7, fontSize: 13, cursor: 'pointer', fontFamily: 'inherit' }
