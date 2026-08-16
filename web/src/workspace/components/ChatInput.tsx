import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { agentKeys, createAgent, listAvailable as listAvailableAgents, listSubagentCandidates } from '../../api/agents'
import { listCatalog as listMcpCatalog, mcpKeys } from '../../api/mcp'
import { errorMessage } from '../../api/request'
import { listAvailable as listAvailableSkills, skillKeys } from '../../api/skills'
import type { AgentConfig, SkillReference } from '../../api/types'
import { listingCaption } from '../agent'
import { DATA_LEAVES_CAMPUS, mountedMcps } from '../mcp'
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
  const [subagentIds, setSubagentIds] = useState<string[]>([])
  const [mcpIds, setMcpIds] = useState<string[]>([])
  const [configError, setConfigError] = useState('')
  const [isSending, setIsSending] = useState(false)
  const [sceneName, setSceneName] = useState('')
  const [saveNotice, setSaveNotice] = useState('')
  const queryClient = useQueryClient()

  // 只在配置面板真的展开时拉目录 —— 大多数提问不碰配置。
  const agents = useQuery({ queryKey: agentKeys.available(), queryFn: listAvailableAgents, enabled: configOpen })
  const skills = useQuery({ queryKey: skillKeys.available(), queryFn: listAvailableSkills, enabled: configOpen })
  const subagents = useQuery({ queryKey: agentKeys.subagentCandidates(), queryFn: listSubagentCandidates, enabled: configOpen })
  const mcps = useQuery({ queryKey: mcpKeys.catalog(), queryFn: listMcpCatalog, enabled: configOpen })
  const selectedAgent = (agents.data ?? []).find(one => one.id === agentId)
  const selectedSkills = (skills.data ?? []).filter(one => skillIds.includes(one.id))
  const selectedSubagents = (subagents.data ?? []).filter(one => subagentIds.includes(one.id))
  const selectedMcps = (mcps.data ?? []).filter(one => mcpIds.includes(one.id))
  // **两条路径都要算进来**：直接勾的，以及所选智能体自带的。只算前一条的话，
  // 教师以为自己什么都没勾，而那个场景背后连着一台校外机器
  const mountedMcpList = mountedMcps([mode === 'agent' ? selectedAgent : undefined, ...selectedSubagents], selectedMcps)
  const tooManyMcps = mountedMcpList.length > 3
  const mountedSkills = mergedSkillNames(selectedAgent?.skill_refs ?? [], selectedSkills)
  const mountedSubagents = mergedSubagentNames(selectedAgent?.subagent_refs ?? [], selectedSubagents)
  const duplicateName = duplicateSkillName(selectedAgent?.skill_refs ?? [], selectedSkills)
  const duplicateSubagent = duplicateSubagentName(selectedAgent?.subagent_refs ?? [], selectedSubagents)
  const tooMany = mountedSkills.length > 10
  const tooManySubagents = mountedSubagents.length > 5
  const saveScene = useMutation({
    mutationFn: () => {
      const name = sceneName.trim()
      if (!name) throw new Error('请输入场景名称')
      if (duplicateName || tooMany || duplicateSubagent || tooManySubagents || tooManyMcps) throw new Error('请先修正当前配置后再保存')
      const systemPrompt = mode === 'agent' ? selectedAgent?.system_prompt : mode === 'custom' ? prompt : threadAgentConfig?.system_prompt || '你是一名严谨的金融分析助手。'
      if (!systemPrompt) throw new Error('当前智能体还没有可保存的提示词')
      return createAgent({
        name,
        description: '从分析对话中保存的可复用场景配置。',
        subject: '金融分析',
        system_prompt: systemPrompt,
        skills: [...new Set([...(selectedAgent?.skill_refs?.map(one => one.skill_id) ?? []), ...skillIds])],
        subagents: [...new Set([...(selectedAgent?.subagent_refs?.map(one => one.agent_id) ?? []), ...subagentIds])],
        mcps: [...new Set([...(selectedAgent?.mcp_refs?.map(one => one.server_id) ?? []), ...mcpIds])],
      })
    },
    async onSuccess() {
      setSceneName('')
      setSaveNotice('已保存到我的场景')
      await queryClient.invalidateQueries({ queryKey: agentKeys.mine() })
    },
    onError(error) {
      setSaveNotice(error instanceof Error ? error.message : errorMessage(error, '保存场景失败'))
    },
  })

  const toggleSubagent = (subagentId: string, checked: boolean) => {
    setSubagentIds(current => checked ? [...current, subagentId] : current.filter(one => one !== subagentId))
    if (checked && mode === 'inherit') setMode('default')
    setConfigError('')
  }

  const toggleMcp = (serverId: string, checked: boolean) => {
    setMcpIds(current => checked ? [...current, serverId] : current.filter(one => one !== serverId))
    if (checked && mode === 'inherit') setMode('default')
    setConfigError('')
  }

  const toggleSkill = (skillId: string, checked: boolean) => {
    setSkillIds(current => checked ? [...current, skillId] : current.filter(one => one !== skillId))
    if (checked && mode === 'inherit') setMode('default')
    setConfigError('')
  }

  const handleSend = async () => {
    const content = text.trim()
    if (!content || disabled || isRunning || isSending || !onSend) return
    const error = mode === 'custom' ? systemPromptError(prompt) : mode === 'agent' ? agentChoiceError(agentId) : null
    if (error || duplicateName || tooMany || duplicateSubagent || tooManySubagents || tooManyMcps) {
      setConfigError(error ?? (duplicateName ? `Skill 名称冲突：${duplicateName}` : duplicateSubagent ? `子智能体名称冲突：${duplicateSubagent}` : tooManySubagents ? '一次最多挂载 5 个子智能体' : tooManyMcps ? '一次最多挂载 3 个 MCP' : '一次最多挂载 10 个 Skill'))
      setConfigOpen(true)
      return
    }
    setConfigError('')
    setIsSending(true)
    try {
      await onSend(content, buildRunAgentConfig(mode, prompt, agentId, skillIds, subagentIds, mcpIds))
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
        <button type="button" aria-label="本轮智能体配置" aria-expanded={configOpen} onClick={() => setConfigOpen(open => !open)} style={{ border: 'none', background: 'transparent', color: 'var(--action)', fontSize: 12, padding: '2px 0 8px', cursor: 'pointer', fontFamily: 'inherit' }}>
          配置智能体 · {AGENT_CONFIG_MODE_LABEL[mode]}{skillIds.length ? ` · ${skillIds.length} 个 Skill` : ''}{subagentIds.length ? ` · ${subagentIds.length} 个子智能体` : ''}{mountedMcpList.length ? ` · ${mountedMcpList.length} 个 MCP` : ''}
        </button>
        {configOpen && <><div onClick={() => setConfigOpen(false)} style={{ position: 'fixed', inset: 0, background: 'rgba(13,24,41,0.35)', zIndex: 300 }} /><div role="dialog" aria-label="智能体配置" style={{ position: 'fixed', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', width: 620, maxWidth: 'calc(100vw - 32px)', maxHeight: 'calc(100vh - 48px)', overflowY: 'auto', padding: '18px 20px', border: '1px solid var(--border)', borderRadius: 12, background: 'var(--surface)', boxShadow: '0 16px 48px rgba(11,46,92,0.22)', zIndex: 301 }}><div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}><strong style={{ fontSize: 16, color: 'var(--text-primary)' }}>本轮智能体配置</strong><button type="button" aria-label="关闭配置" onClick={() => setConfigOpen(false)} style={{ border: 'none', background: 'transparent', color: 'var(--text-muted)', fontSize: 20, cursor: 'pointer' }}>×</button></div><div style={{ padding: '10px 12px', border: '1px solid var(--action-border)', borderRadius: 7, background: 'var(--action-light)' }}>
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
            {mountedSkills.length > 0 && <div style={{ ...hintStyle, marginTop: 8 }}>最终挂载：{mountedSkills.join('、')}</div>}
          </div>
          <div style={{ marginTop: 12, paddingTop: 10, borderTop: '1px solid var(--action-border)' }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 7 }}>本轮子智能体（可多选）</div>
            {subagents.isPending && <div style={hintStyle}>正在加载可用的子智能体…</div>}
            {subagents.isError && <div role="alert" style={{ ...hintStyle, color: '#DC2626' }}>{errorMessage(subagents.error)}</div>}
            {!subagents.isPending && !subagents.isError && (subagents.data ?? []).length === 0 && <div style={hintStyle}>还没有可挂载的子智能体。</div>}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 6 }}>
              {(subagents.data ?? []).map(one => <label key={one.id} style={{ display: 'flex', gap: 6, alignItems: 'flex-start', fontSize: 12, color: 'var(--text-secondary)' }}>
                <input type="checkbox" aria-label={one.name} checked={subagentIds.includes(one.id)} onChange={event => toggleSubagent(one.id, event.target.checked)} />
                <span><strong>{one.name}</strong><br /><span style={{ fontSize: 10, color: 'var(--text-muted)' }}>{one.owner_name} · v{one.version}</span></span>
              </label>)}
            </div>
            {mountedSubagents.length > 0 && <div style={{ ...hintStyle, marginTop: 8 }}>最终挂载：{mountedSubagents.join('、')}</div>}
          </div>
          <div style={{ marginTop: 12, paddingTop: 10, borderTop: '1px solid var(--action-border)' }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 7 }}>本轮 MCP（可多选，最多 3 个）</div>
            {mcps.isPending && <div style={hintStyle}>正在加载 MCP 目录…</div>}
            {mcps.isError && <div role="alert" style={{ ...hintStyle, color: '#DC2626' }}>{errorMessage(mcps.error)}</div>}
            {!mcps.isPending && !mcps.isError && (mcps.data ?? []).length === 0 && <div style={hintStyle}>还没有放行的 MCP。</div>}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 6 }}>
              {(mcps.data ?? []).map(one => <label key={one.id} style={{ display: 'flex', gap: 6, alignItems: 'flex-start', fontSize: 12, color: 'var(--text-secondary)' }}>
                <input type="checkbox" aria-label={one.name} checked={mcpIds.includes(one.id)} onChange={event => toggleMcp(one.id, event.target.checked)} />
                <span><strong>{one.name}</strong><br /><span style={{ fontSize: 10, color: 'var(--text-muted)' }}>{one.tool_names.length} 个工具 · 校外</span></span>
              </label>)}
            </div>
            {mountedMcpList.length > 0 && <div data-testid="mcp-outbound" style={outboundStyle}>
              <div style={{ fontWeight: 600, marginBottom: 4 }}>{DATA_LEAVES_CAMPUS}</div>
              <div>最终挂载：{mountedMcpList.map(one => one.via ? `${one.name}（来自 ${one.via}）` : one.name).join('、')}</div>
            </div>}
          </div>
          {configError && <div role="alert" style={{ marginTop: 6, fontSize: 11, color: '#DC2626' }}>{configError}</div>}
          <div style={{ marginTop: 14, paddingTop: 12, borderTop: '1px solid var(--border)', display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            <input value={sceneName} onChange={event => { setSceneName(event.target.value); setSaveNotice('') }} placeholder="场景名称" style={{ ...selectStyle, flex: 1, minWidth: 180 }} />
            <button type="button" onClick={() => saveScene.mutate()} disabled={saveScene.isPending} style={{ padding: '8px 12px', border: '1px solid var(--action-border)', borderRadius: 6, background: 'var(--surface)', color: 'var(--action)', cursor: saveScene.isPending ? 'default' : 'pointer', fontFamily: 'inherit', fontSize: 12 }}>{saveScene.isPending ? '保存中…' : '保存到我的场景库'}</button>
            <button type="button" onClick={() => setConfigOpen(false)} style={{ padding: '8px 12px', border: 'none', borderRadius: 6, background: 'var(--action)', color: '#fff', cursor: 'pointer', fontFamily: 'inherit', fontSize: 12 }}>完成</button>
            {saveNotice && <span style={{ width: '100%', fontSize: 11, color: saveNotice.startsWith('已') ? '#059669' : '#DC2626' }}>{saveNotice}</span>}
          </div>
        </div></div></>}
        <textarea value={text} disabled={disabled || isSending} onChange={event => setText(event.target.value)} onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); void handleSend() } }} placeholder={disabled ? '请先新建一个分析对话' : '输入分析需求…（Enter 发送，Shift+Enter 换行）'} style={{ width: '100%', minHeight: 52, maxHeight: 160, border: 'none', fontSize: 14, color: 'var(--text-primary)', background: 'transparent', resize: 'none', fontFamily: 'inherit', lineHeight: 1.65, boxSizing: 'border-box' }} />
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', marginTop: 8, paddingTop: 8, borderTop: '1px solid var(--border-light)' }}>
          {isRunning ? <button type="button" onClick={onStop} aria-label="停止分析" style={{ width: 40, height: 40, borderRadius: 8, background: 'var(--danger)', border: 'none', color: '#fff', cursor: 'pointer', display: 'grid', placeItems: 'center' }}>■</button> : <button type="button" disabled={disabled || isSending || !text.trim()} onClick={() => void handleSend()} aria-label="发送" style={{ width: 40, height: 40, borderRadius: 8, background: 'var(--action)', border: 'none', color: '#fff', cursor: disabled || isSending || !text.trim() ? 'default' : 'pointer', opacity: disabled || isSending || !text.trim() ? 0.5 : 1, display: 'grid', placeItems: 'center' }}>↗</button>}
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

function mergedSubagentNames(agentRefs: readonly { agent_id: string; version: number; name: string }[], selected: readonly { id: string; version: number; name: string }[]): string[] {
  const refs = [
    ...agentRefs.map(one => ({ key: `${one.agent_id}:${one.version}:${one.name}`, name: one.name })),
    ...selected.map(one => ({ key: `${one.id}:${one.version}:${one.name}`, name: one.name })),
  ]
  return [...new Map(refs.map(one => [one.key, one.name])).values()]
}

function duplicateSubagentName(agentRefs: readonly { agent_id: string; version: number; name: string }[], selected: readonly { id: string; version: number; name: string }[]): string | null {
  const seen = new Map<string, string>()
  for (const one of [
    ...agentRefs.map(ref => ({ key: `${ref.agent_id}:${ref.version}:${ref.name}`, name: ref.name })),
    ...selected.map(agent => ({ key: `${agent.id}:${agent.version}:${agent.name}`, name: agent.name })),
  ]) {
    const existing = seen.get(one.name)
    if (existing && existing !== one.key) return one.name
    seen.set(one.name, one.key)
  }
  return null
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
const outboundStyle: React.CSSProperties = { marginTop: 8, padding: '8px 10px', border: '1px solid #FDE68A', borderRadius: 6, background: '#FFFBEB', color: '#92400E', fontSize: 11, lineHeight: 1.6 }
const hintStyle: React.CSSProperties = { marginTop: 6, fontSize: 11, color: 'var(--text-muted)', lineHeight: 1.6 }
