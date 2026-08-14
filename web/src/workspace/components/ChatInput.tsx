import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { agentKeys, listAvailable } from '../../api/agents'
import { errorMessage } from '../../api/request'
import type { AgentConfig } from '../../api/types'
import { listingCaption } from '../agent'
import {
  AGENT_CONFIG_MODES,
  AGENT_CONFIG_MODE_LABEL,
  MAX_SYSTEM_PROMPT_LENGTH,
  agentChoiceError,
  buildRunAgentConfig,
  describeAgentConfig,
  systemPromptError,
  type AgentConfigMode,
} from '../config'

interface ChatInputProps {
  isRunning?: boolean
  disabled?: boolean
  threadAgentConfig?: AgentConfig
  /** 从广场「用它开始分析」跳过来时带的那个 agent，直接把配置面板预设成引用它。 */
  initialAgentId?: string
  onSend?: (text: string, agentConfig: AgentConfig | undefined) => Promise<void>
  onStop?: () => void
}

export function ChatInput({ isRunning = false, disabled = false, threadAgentConfig, initialAgentId, onSend, onStop }: ChatInputProps) {
  const [text, setText] = useState('')
  const [configOpen, setConfigOpen] = useState(Boolean(initialAgentId))
  const [mode, setMode] = useState<AgentConfigMode>(initialAgentId ? 'agent' : 'inherit')
  const [prompt, setPrompt] = useState('')
  const [agentId, setAgentId] = useState(initialAgentId ?? '')
  const [configError, setConfigError] = useState('')
  const [isSending, setIsSending] = useState(false)

  // 只在配置面板真的展开时才去拉这一份 —— 大多数提问不碰配置
  const available = useQuery({ queryKey: agentKeys.available(), queryFn: listAvailable, enabled: configOpen })

  const handleSend = async () => {
    const content = text.trim()
    if (!content || disabled || isRunning || isSending || !onSend) return
    const error = mode === 'custom' ? systemPromptError(prompt) : mode === 'agent' ? agentChoiceError(agentId) : null
    if (error) {
      setConfigError(error)
      setConfigOpen(true)
      return
    }
    setConfigError('')
    setIsSending(true)
    try {
      await onSend(content, buildRunAgentConfig(mode, prompt, agentId))
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
          {configOpen ? '▾' : '▸'} 本轮智能体配置 · {AGENT_CONFIG_MODE_LABEL[mode]}
        </button>
        {configOpen && <div style={{ padding: '10px 12px', marginBottom: 10, border: '1px solid var(--action-border)', borderRadius: 7, background: 'var(--action-light)' }}>
          <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginBottom: mode === 'inherit' ? 0 : 10 }}>
            {AGENT_CONFIG_MODES.map(value => <label key={value} style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 12, color: 'var(--text-secondary)', cursor: 'pointer' }}>
              <input type="radio" name="agent-config-mode" value={value} checked={mode === value} onChange={() => { setMode(value); setConfigError('') }} />
              {AGENT_CONFIG_MODE_LABEL[value]}
            </label>)}
          </div>
          {mode === 'inherit' && <div style={{ marginTop: 8, fontSize: 11, color: 'var(--text-muted)' }}>
            本轮不传 <code>agent_config</code>。会话当前默认：{describeAgentConfig(threadAgentConfig, available.data ?? [])}
          </div>}
          {mode === 'default' && <div style={{ marginTop: 8, fontSize: 11, color: 'var(--text-muted)' }}>
            本轮显式传 <code>{'{}'}</code>，即使会话设过自定义提示词或选过智能体也不继承。
          </div>}
          {mode === 'agent' && <>
            <select
              aria-label="选择智能体"
              value={agentId}
              onChange={event => { setAgentId(event.target.value); setConfigError('') }}
              style={{ width: '100%', padding: '7px 10px', border: '1px solid var(--border)', borderRadius: 6, fontSize: 12, fontFamily: 'inherit', background: 'var(--surface)', color: 'var(--text-primary)', boxSizing: 'border-box' }}
            >
              <option value="">-- 请选择 --</option>
              {(available.data ?? []).map(one => (
                <option key={one.id} value={one.id}>{one.name}（{listingCaption(one)}）</option>
              ))}
            </select>
            <div style={{ marginTop: 6, fontSize: 11, color: 'var(--text-muted)', lineHeight: 1.6 }}>
              {available.isPending && '正在加载可用的智能体…'}
              {available.isError && <span style={{ color: '#DC2626' }}>{errorMessage(available.error)}</span>}
              {!available.isPending && !available.isError && (available.data ?? []).length === 0 && '还没有你能引用的智能体。去「智能体广场」看看，或自己建一个。'}
              {!available.isPending && (available.data ?? []).length > 0 && '提交那一刻会把它当前的版本冻结进这一轮，之后作者再改也不影响已经跑过的分析。'}
            </div>
          </>}
          {mode === 'custom' && <>
            <textarea value={prompt} maxLength={MAX_SYSTEM_PROMPT_LENGTH} onChange={event => { setPrompt(event.target.value); setConfigError('') }} placeholder="例如：你是一名谨慎的金融风险分析师…" style={{ width: '100%', minHeight: 86, boxSizing: 'border-box', resize: 'vertical', border: '1px solid var(--border)', borderRadius: 6, padding: 10, font: 'inherit', fontSize: 12, lineHeight: 1.6, color: 'var(--text-primary)' }} />
            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 4, fontSize: 11, color: 'var(--text-muted)' }}>{prompt.length} / {MAX_SYSTEM_PROMPT_LENGTH}</div>
          </>}
          {configError && <div role="alert" style={{ marginTop: 6, fontSize: 11, color: '#DC2626' }}>{configError}</div>}
        </div>}
        <textarea value={text} disabled={disabled || isSending} onChange={event => setText(event.target.value)} onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); void handleSend() } }} placeholder={disabled ? '请先新建一个分析对话' : '输入分析需求…（Enter 发送，Shift+Enter 换行）'} style={{ width: '100%', minHeight: 52, maxHeight: 160, border: 'none', outline: 'none', fontSize: 14, color: 'var(--text-primary)', background: 'transparent', resize: 'none', fontFamily: 'inherit', lineHeight: 1.65, boxSizing: 'border-box' }} />
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', marginTop: 8, paddingTop: 8, borderTop: '1px solid var(--border-light)' }}>
          {isRunning ? <button type="button" onClick={onStop} title="停止分析" style={{ width: 36, height: 36, borderRadius: 7, background: '#DC2626', border: 'none', color: '#fff', cursor: 'pointer' }}>■</button> : <button type="button" disabled={disabled || isSending || !text.trim()} onClick={() => void handleSend()} title="发送" style={{ width: 36, height: 36, borderRadius: 7, background: 'var(--action)', border: 'none', color: '#fff', cursor: disabled || isSending || !text.trim() ? 'default' : 'pointer', opacity: disabled || isSending || !text.trim() ? 0.5 : 1 }}>↗</button>}
        </div>
      </div>
    </div>
  )
}
