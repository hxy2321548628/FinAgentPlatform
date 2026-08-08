import { useState, useRef } from 'react'

interface ChatInputProps {
  isRunning?: boolean
  onSend?: (text: string, files: string[]) => void
  onStop?: () => void
}

export function ChatInput({ isRunning = false, onSend, onStop }: ChatInputProps) {
  const [text, setText] = useState('')
  const [attachments, setAttachments] = useState<string[]>([])
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleSend = () => {
    if (!text.trim() && attachments.length === 0) return
    onSend?.(text, attachments)
    setText('')
    setAttachments([])
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []).map(f => f.name)
    setAttachments(prev => [...prev, ...files])
    e.target.value = ''
  }

  return (
    <div style={{ padding: '12px 24px 16px', borderTop: '1px solid var(--border)', background: 'var(--bg)', flexShrink: 0 }}>
      <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, padding: '12px 16px', boxShadow: '0 2px 8px rgba(11,46,92,0.06)' }}>
        <textarea
          value={text}
          onChange={e => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="输入分析需求，或描述你想做的事情...（Enter 发送，Shift+Enter 换行）"
          style={{ width: '100%', minHeight: 52, maxHeight: 160, border: 'none', outline: 'none', fontSize: 14, color: 'var(--text-primary)', background: 'transparent', resize: 'none' as const, fontFamily: 'inherit', lineHeight: 1.65, boxSizing: 'border-box' as const }}
        />

        {attachments.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap' as const, gap: 6, marginBottom: 10 }}>
            {attachments.map(name => (
              <div key={name} style={{ display: 'inline-flex', alignItems: 'center', gap: 5, padding: '3px 10px', background: 'var(--action-light)', border: '1px solid var(--action-border)', borderRadius: 5, fontSize: 12, color: 'var(--action)' }}>
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>
                {name}
                <button onClick={() => setAttachments(prev => prev.filter(n => n !== name))} style={{ background: 'none', border: 'none', color: 'var(--action)', cursor: 'pointer', padding: 0, fontSize: 12, lineHeight: 1 }}>×</button>
              </div>
            ))}
          </div>
        )}

        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 8, paddingTop: 8, borderTop: '1px solid var(--border-light)' }}>
          <div style={{ display: 'flex', gap: 6 }}>
            <input ref={fileInputRef} type="file" multiple accept=".csv,.xlsx,.xls,.pdf,.txt" style={{ display: 'none' }} onChange={handleFileChange} />
            <button
              onClick={() => fileInputRef.current?.click()}
              style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '5px 10px', border: '1px solid var(--border)', borderRadius: 5, background: 'transparent', fontSize: 12, color: 'var(--text-secondary)', cursor: 'pointer', fontFamily: 'inherit' }}
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>
              附件
            </button>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>Enter 发送</span>
            {isRunning ? (
              <button onClick={onStop} style={{ width: 36, height: 36, borderRadius: 7, background: '#DC2626', border: 'none', color: '#fff', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><rect x="4" y="4" width="16" height="16"/></svg>
              </button>
            ) : (
              <button onClick={handleSend} style={{ width: 36, height: 36, borderRadius: 7, background: 'var(--action)', border: 'none', color: '#fff', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
