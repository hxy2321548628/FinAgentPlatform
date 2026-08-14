import { useState } from 'react'
import type { AgentConfig } from '../../api/types'
import {
  MAX_SYSTEM_PROMPT_LENGTH,
  buildRunAgentConfig,
  systemPromptError,
  type AgentConfigMode,
} from '../config'

interface ChatInputProps {
  isRunning?: boolean
  disabled?: boolean
  threadAgentConfig?: AgentConfig
  onSend?: (text: string, agentConfig: AgentConfig | undefined) => Promise<void>
  onStop?: () => void
}

const MODE_LABEL: Record<AgentConfigMode, string> = {
  inherit: '继承会话默认',
  default: '恢复平台默认',
  custom: '本轮自定义',
}

export function ChatInput({ isRunning = false, disabled = false, threadAgentConfig, onSend, onStop }: ChatInputProps) {
  const [text, setText] = useState('')
  const [configOpen, setConfigOpen] = useState(false)
  const [mode, setMode] = useState<AgentConfigMode>('inherit')
  const [prompt, setPrompt] = useState('')
  const [configError, setConfigError] = useState('')
  const [isSending, setIsSending] = useState(false)

  const handleSend = async () => {
    const content = text.trim()
    if (!content || disabled || isRunning || isSending || !onSend) return
    if (mode === 'custom') {
      const error = systemPromptError(prompt)
      if (error) {
        setConfigError(error)
        setConfigOpen(true)
        return
      }
    }
    setConfigError('')
    setIsSending(true)
    try {
      await onSend(content, buildRunAgentConfig(mode, prompt))
      setText('')
    } catch {
      // mutation 状态负责显示错误；保留输入供用户修改或重试。
    } finally {
      setIsSending(false)
    }
  }

  return (
    <div style={{ padding: '12px 24px 16px', borderTop: '1px solid var(--border)', background: 'var(--bg)', flexShrink: 0 }}>
      <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, padding: '10px 16px 12px', boxShadow: '0 2px 8px rgba(11,46,92,0.06)' }}>
        <button type="button" aria-expanded={configOpen} onClick={() => setConfigOpen(open => !open)} style={{ border: 'none', background: 'transparent', color: 'var(--action)', fontSize: 12, padding: '2px 0 8px', cursor: 'pointer', fontFamily: 'inherit' }}>
          {configOpen ? '▾' : '▸'} 本轮智能体配置 · {MODE_LABEL[mode]}
        </button>
        {configOpen && <div style={{ padding: '10px 12px', marginBottom: 10, border: '1px solid var(--action-border)', borderRadius: 7, background: 'var(--action-light)' }}>
          <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginBottom: mode === 'custom' ? 10 : 0 }}>
            {(['inherit', 'default', 'custom'] as const).map(value => <label key={value} style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 12, color: 'var(--text-secondary)', cursor: 'pointer' }}>
              <input type="radio" name="agent-config-mode" value={value} checked={mode === value} onChange={() => { setMode(value); setConfigError('') }} />
              {MODE_LABEL[value]}
            </label>)}
          </div>
          {mode === 'inherit' && <div style={{ marginTop: 8, fontSize: 11, color: 'var(--text-muted)' }}>
            本轮不传 <code>agent_config</code>。会话当前默认：{threadAgentConfig?.system_prompt || '平台默认角色'}
          </div>}
          {mode === 'default' && <div style={{ marginTop: 8, fontSize: 11, color: 'var(--text-muted)' }}>
            本轮显式传 <code>{'{}'}</code>，即使会话设过自定义提示词也不继承。
          </div>}
          {mode === 'custom' && <>
            <textarea value={prompt} maxLength={MAX_SYSTEM_PROMPT_LENGTH} onChange={event => { setPrompt(event.target.value); setConfigError('') }} placeholder="例如：你是一名谨慎的金融风险分析师…" style={{ width: '100%', minHeight: 86, boxSizing: 'border-box', resize: 'vertical', border: '1px solid var(--border)', borderRadius: 6, padding: 10, font: 'inherit', fontSize: 12, lineHeight: 1.6, color: 'var(--text-primary)' }} />
            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 4, fontSize: 11 }}><span style={{ color: '#DC2626' }}>{configError}</span><span style={{ color: 'var(--text-muted)' }}>{prompt.length} / {MAX_SYSTEM_PROMPT_LENGTH}</span></div>
          </>}
        </div>}
        <textarea value={text} disabled={disabled || isSending} onChange={event => setText(event.target.value)} onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); void handleSend() } }} placeholder={disabled ? '请先新建一个分析对话' : '输入分析需求…（Enter 发送，Shift+Enter 换行）'} style={{ width: '100%', minHeight: 52, maxHeight: 160, border: 'none', outline: 'none', fontSize: 14, color: 'var(--text-primary)', background: 'transparent', resize: 'none', fontFamily: 'inherit', lineHeight: 1.65, boxSizing: 'border-box' }} />
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', marginTop: 8, paddingTop: 8, borderTop: '1px solid var(--border-light)' }}>
          {isRunning ? <button type="button" onClick={onStop} title="停止分析" style={{ width: 36, height: 36, borderRadius: 7, background: '#DC2626', border: 'none', color: '#fff', cursor: 'pointer' }}>■</button> : <button type="button" disabled={disabled || isSending || !text.trim()} onClick={() => void handleSend()} title="发送" style={{ width: 36, height: 36, borderRadius: 7, background: 'var(--action)', border: 'none', color: '#fff', cursor: disabled || isSending || !text.trim() ? 'default' : 'pointer', opacity: disabled || isSending || !text.trim() ? 0.5 : 1 }}>↗</button>}
        </div>
      </div>
    </div>
  )
}
