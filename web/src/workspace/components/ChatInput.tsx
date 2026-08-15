import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { agentKeys, listAvailable as listAvailableAgents } from '../../api/agents'
import { errorMessage } from '../../api/request'
import { listAvailable as listAvailableSkills, skillKeys } from '../../api/skills'
import type { AgentConfig, SkillReference } from '../../api/types'
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
  const [skillIds, setSkillIds] = useState<string[]>([])
  const [configError, setConfigError] = useState('')
  const [isSending, setIsSending] = useState(false)

  // 只在配置面板真的展开时拉目录 —— 大多数提问不碰配置。
  const agents = useQuery({ queryKey: agentKeys.available(), queryFn: listAvailableAgents, enabled: configOpen })
  const skills = useQuery({ queryKey: skillKeys.available(), queryFn: listAvailableSkills, enabled: configOpen })
  const selectedAgent = (agents.data ?? []).find(one => one.id === agentId)
  const selectedSkills = (skills.data ?? []).filter(one => skillIds.includes(one.id))
  const mounted = mergedSkillNames(selectedAgent?.skill_refs ?? [], selectedSkills)
  const duplicateName = duplicateSkillName(selectedAgent?.skill_refs ?? [], selectedSkills)
  const tooMany = mounted.length > 10

  const toggleSkill = (skillId: string, checked: boolean) => {
    setSkillIds(current => checked ? [...current, skillId] : current.filter(one => one !== skillId))
    if (checked && mode === 'inherit') setMode('default')
    setConfigError('')
  }

  const handleSend = async () => {
    const content = text.trim()
    if (!content || disabled || isRunning || isSending || !onSend) return
    const error = mode === 'custom' ? systemPromptError(prompt) : mode === 'agent' ? agentChoiceError(agentId) : null
    if (error || duplicateName || tooMany) {
      setConfigError(error ?? (duplicateName ? `Skill 名称冲突：${duplicateName}` : '一次最多挂载 10 个 Skill'))
      setConfigOpen(true)
      return
    }
    setConfigError('')
    setIsSending(true)
    try {
      await onSend(content, buildRunAgentConfig(mode, prompt, agentId, skillIds))
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
          {configOpen ? '▾' : '▸'} 本轮智能体配置 · {AGENT_CONFIG_MODE_LABEL[mode]}{skillIds.length ? ` · ${skillIds.length} 个 Skill` : ''}
        </button>
        {configOpen && <div style={{ padding: '10px 12px', marginBottom: 10, border: '1px solid var(--action-border)', borderRadius: 7, background: 'var(--action-light)' }}>
          <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginBottom: mode === 'inherit' ? 0 : 10 }}>
            {AGENT_CONFIG_MODES.map(value => <label key={value} style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 12, color: 'var(--text-secondary)', cursor: 'pointer' }}>
              <input type="radio" name="agent-config-mode" value={value} checked={mode === value} onChange={() => { setMode(value); setConfigError('') }} />
              {AGENT_CONFIG_MODE_LABEL[value]}
            </label>)}
          </div>
          {mode === 'inherit' && <div style={{ marginTop: 8, fontSize: 11, color: 'var(--text-muted)' }}>
            本轮不传 <code>agent_config</code>。会话当前默认：{describeAgentConfig(threadAgentConfig, agents.data ?? [])}
          </div>}
          {mode === 'default' && <div style={{ marginTop: 8, fontSize: 11, color: 'var(--text-muted)' }}>
            本轮显式覆盖为平台默认角色；可以只挂下面选择的 Skill。
          </div>}
          {mode === 'agent' && <>
            <select aria-label="选择智能体" value={agentId} onChange={event => { setAgentId(event.target.value); setConfigError('') }} style={selectStyle}>
              <option value="">-- 请选择 --</option>
              {(agents.data ?? []).map(one => <option key={one.id} value={one.id}>{one.name}（{listingCaption(one)}）</option>)}
            </select>
            <div style={hintStyle}>
              {agents.isPending && '正在加载可用的智能体…'}
              {agents.isError && <span style={{ color: '#DC2626' }}>{errorMessage(agents.error)}</span>}
              {!agents.isPending && !agents.isError && (agents.data ?? []).length === 0 && '还没有你能引用的智能体。去「智能体广场」看看，或自己建一个。'}
              {!agents.isPending && (agents.data ?? []).length > 0 && '提交时会冻结智能体版本及它自带的 Skill。'}
            </div>
          </>}
          {mode === 'custom' && <>
            <textarea value={prompt} maxLength={MAX_SYSTEM_PROMPT_LENGTH} onChange={event => { setPrompt(event.target.value); setConfigError('') }} placeholder="例如：你是一名谨慎的金融风险分析师…" style={{ ...selectStyle, minHeight: 86, resize: 'vertical', lineHeight: 1.6 }} />
            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 4, fontSize: 11, color: 'var(--text-muted)' }}>{prompt.length} / {MAX_SYSTEM_PROMPT_LENGTH}</div>
          </>}

          <div style={{ marginTop: 12, paddingTop: 10, borderTop: '1px solid var(--action-border)' }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 7 }}>本轮 Skill（可多选）</div>
            {skills.isPending && <div style={hintStyle}>正在加载可用 Skill…</div>}
            {skills.isError && <div role="alert" style={{ ...hintStyle, color: '#DC2626' }}>{errorMessage(skills.error)}</div>}
            {!skills.isPending && !skills.isError && (skills.data ?? []).length === 0 && <div style={hintStyle}>还没有你能使用的 Skill。</div>}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 6 }}>
              {(skills.data ?? []).map(one => <label key={one.id} style={{ display: 'flex', gap: 6, alignItems: 'flex-start', fontSize: 12, color: 'var(--text-secondary)' }}>
                <input type="checkbox" aria-label={one.name} checked={skillIds.includes(one.id)} onChange={event => toggleSkill(one.id, event.target.checked)} />
                <span><strong>{one.name}</strong><br /><span style={{ fontSize: 10, color: 'var(--text-muted)' }}>{one.owner_name} · v{one.version}</span></span>
              </label>)}
            </div>
            {mounted.length > 0 && <div style={{ ...hintStyle, marginTop: 8 }}>最终挂载：{mounted.join('、')}</div>}
          </div>
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

function mergedSkillNames(agentRefs: readonly SkillReference[], selected: readonly { id: string; version: number; name: string }[]): string[] {
  const refs = [
    ...agentRefs.map(one => ({ key: `${one.skill_id}:${one.version}:${one.name}`, name: one.name })),
    ...selected.map(one => ({ key: `${one.id}:${one.version}:${one.name}`, name: one.name })),
  ]
  return [...new Map(refs.map(one => [one.key, one.name])).values()]
}

function duplicateSkillName(agentRefs: readonly SkillReference[], selected: readonly { id: string; version: number; name: string }[]): string | null {
  const seen = new Map<string, string>()
  for (const one of [
    ...agentRefs.map(ref => ({ key: `${ref.skill_id}:${ref.version}:${ref.name}`, name: ref.name })),
    ...selected.map(skill => ({ key: `${skill.id}:${skill.version}:${skill.name}`, name: skill.name })),
  ]) {
    const existing = seen.get(one.name)
    if (existing && existing !== one.key) return one.name
    seen.set(one.name, one.key)
  }
  return null
}

const selectStyle: React.CSSProperties = { width: '100%', padding: '7px 10px', border: '1px solid var(--border)', borderRadius: 6, fontSize: 12, fontFamily: 'inherit', background: 'var(--surface)', color: 'var(--text-primary)', boxSizing: 'border-box' }
const hintStyle: React.CSSProperties = { marginTop: 6, fontSize: 11, color: 'var(--text-muted)', lineHeight: 1.6 }
