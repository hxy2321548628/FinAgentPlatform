import { useState } from 'react'

interface ChatInputProps {
  isRunning?: boolean
  onSend?: (text: string) => void
  onStop?: () => void
}

export function ChatInput({ isRunning = false, onSend, onStop }: ChatInputProps) {
  const [text, setText] = useState('')

  const handleSend = () => {
    if (!text.trim()) return
    onSend?.(text)
    setText('')
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
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


        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', marginTop: 8, paddingTop: 8, borderTop: '1px solid var(--border-light)' }}>
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
