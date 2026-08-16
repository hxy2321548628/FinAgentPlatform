import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { agentKeys, createAgent, listAvailable as listAvailableAgents, listSubagentCandidates } from '../../api/agents'
import { listCatalog as listMcpCatalog, mcpKeys } from '../../api/mcp'
import { errorMessage } from '../../api/request'
import { listAvailable as listAvailableSkills, skillKeys } from '../../api/skills'
import { threadKeys, updateThread } from '../../api/threads'
import type { AgentConfig, SkillReference } from '../../api/types'
import { listingCaption } from '../agent'
import { mountedMcps } from '../mcp'
import { useToast } from '../../components/ui/toast-context'
import * as Dialog from '@radix-ui/react-dialog'
import { Button } from '../../components/ui/Button'
import {
  MAX_SYSTEM_PROMPT_LENGTH,
  agentChoiceError,
  buildRunAgentConfig,
  describeAgentConfig,
  systemPromptError,
  type AgentConfigMode,
} from '../config'

const VISIBLE_AGENT_MODES = [
  { value: 'default', label: '平台默认', description: '使用平台基础角色', ariaLabel: '平台默认' },
  { value: 'agent', label: '使用智能体', description: '引用已发布的配置', ariaLabel: '使用智能体' },
  { value: 'custom', label: '自定义提示词', description: '直接编写角色要求', ariaLabel: '使用自定义提示词' },
] as const

interface ChatInputProps {
  isRunning?: boolean
  disabled?: boolean
  /** 所属会话；欢迎页（懒创建）下为 undefined，此时持久化推迟到首次发送建会话时。 */
  threadId?: string
  threadAgentConfig?: AgentConfig
  /** 从广场「用它开始分析」跳过来时带的那个 agent，直接把配置面板预设成引用它。 */
  initialAgentId?: string
  onSend?: (text: string, agentConfig: AgentConfig | undefined) => Promise<void>
  onStop?: () => void
}

interface PickableItem {
  id: string
  name: string
  meta: string
}

/** 把会话里存的配置（快照可能是冻结三元组，也可能是请求态的裸 ID）还原成表单状态。 */
function initialStateFromConfig(config: AgentConfig | null | undefined): {
  mode: AgentConfigMode
  agentId: string
  prompt: string
  skillIds: string[]
  subagentIds: string[]
  mcpIds: string[]
} {
  const base = { agentId: '', prompt: '', skillIds: [] as string[], subagentIds: [] as string[], mcpIds: [] as string[] }
  if (!config) return { mode: 'inherit', ...base }
  const skillIds = (config.skills ?? []).map(one => (typeof one === 'string' ? one : one.skill_id))
  const subagentIds = (config.subagents ?? []).map(one => (typeof one === 'string' ? one : one.agent_id))
  const mcpIds = (config.mcps ?? []).map(one => (typeof one === 'string' ? one : one.server_id))
  const additions = { ...base, skillIds, subagentIds, mcpIds }
  if (config.agent_id) return { ...additions, mode: 'agent', agentId: config.agent_id }
  if (config.system_prompt) return { ...additions, mode: 'custom', prompt: config.system_prompt }
  if (skillIds.length > 0 || subagentIds.length > 0 || mcpIds.length > 0) return { mode: 'default', ...additions }
  return { mode: 'inherit', ...base }
}

/** 选项列表分页大小：选项多时先出一页，其余点「加载更多」。 */
const PICKER_PAGE_SIZE = 12

function ConfigPicker({ title, empty, items, selectedIds, onToggle, searchable }: {
  title: string
  empty: string
  items: PickableItem[]
  selectedIds: string[]
  onToggle: (id: string, checked: boolean) => void
  searchable: boolean
}) {
  const [filter, setFilter] = useState('')
  const [limit, setLimit] = useState(PICKER_PAGE_SIZE)
  useEffect(() => setLimit(PICKER_PAGE_SIZE), [filter])
  const needle = filter.trim().toLowerCase()
  const filtered = needle ? items.filter(one => one.name.toLowerCase().includes(needle)) : items
  const visible = filtered.slice(0, limit)
  return (
    <div className="config-section">
      <div className="config-section-head">
        <span className="config-section-title">{title}</span>
        {selectedIds.length > 0 && <span className="config-section-count">已选 {selectedIds.length}</span>}
      </div>
      {searchable && <input className="config-search" placeholder={`筛选${title}…`} aria-label={`筛选${title}`} value={filter} onChange={event => setFilter(event.target.value)} />}
      {items.length === 0 ? (
        <div className="config-empty">{empty}</div>
      ) : filtered.length === 0 ? (
        <div className="config-empty">没有匹配的项</div>
      ) : (
        <>
          <div className="config-picker-list">
            <div className="config-grid">
              {visible.map(one => {
                const checked = selectedIds.includes(one.id)
                return (
                  <label key={one.id} className={`config-card${checked ? ' checked' : ''}`}>
                    <input type="checkbox" className="config-card-input" checked={checked} aria-label={one.name} onChange={event => onToggle(one.id, event.target.checked)} />
                    <span className="config-card-body">
                      <span className="config-card-name">{one.name}</span>
                      <span className="config-card-meta">{one.meta}</span>
                    </span>
                    <span className="config-card-check" aria-hidden="true">{checked ? '✓' : ''}</span>
                  </label>
                )
              })}
            </div>
          </div>
          {filtered.length > limit && (
            <button type="button" className="config-more" onClick={() => setLimit(current => current + PICKER_PAGE_SIZE)}>
              加载更多（还剩 {filtered.length - limit} 个）
            </button>
          )}
        </>
      )}
    </div>
  )
}

export function ChatInput({ isRunning = false, disabled = false, threadId, threadAgentConfig, initialAgentId, onSend, onStop }: ChatInputProps) {
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
  const { toast } = useToast()
  const queryClient = useQueryClient()
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  // **会话配置回填**：只有用户还没动过配置时才应用，避免覆盖正在进行的编辑。
  // 这是「重新打开同一个会话自动带出上次配置」的入口（kv cache 友好的前提）。
  const configLoadedFromThread = useRef(Boolean(initialAgentId))
  useEffect(() => {
    if (configLoadedFromThread.current || !threadAgentConfig || Object.keys(threadAgentConfig).length === 0) return
    if (mode !== 'inherit' || prompt || skillIds.length > 0 || subagentIds.length > 0 || mcpIds.length > 0) return
    const restored = initialStateFromConfig(threadAgentConfig)
    setMode(restored.mode)
    setAgentId(restored.agentId)
    setPrompt(restored.prompt)
    setSkillIds(restored.skillIds)
    setSubagentIds(restored.subagentIds)
    setMcpIds(restored.mcpIds)
    configLoadedFromThread.current = true
  }, [threadAgentConfig, mode, prompt, skillIds, subagentIds, mcpIds])

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

  // 输入框随内容自动长高，封顶 180px
  useEffect(() => {
    const element = textareaRef.current
    if (!element) return
    element.style.height = 'auto'
    element.style.height = `${Math.min(element.scrollHeight, 180)}px`
  }, [text])

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
      toast({ title: '已保存到我的场景', variant: 'success' })
      await queryClient.invalidateQueries({ queryKey: agentKeys.mine() })
    },
    onError(error) {
      toast({ title: '保存场景失败', description: error instanceof Error ? error.message : errorMessage(error), variant: 'error' })
    },
  })

  const toggleSubagent = (subagentIdValue: string, checked: boolean) => {
    setSubagentIds(current => checked ? [...current, subagentIdValue] : current.filter(one => one !== subagentIdValue))
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

  const combinedConfigError = (): string | null => {
    if (mode === 'custom') return systemPromptError(prompt)
    if (mode === 'agent') return agentChoiceError(agentId)
    if (duplicateName) return `Skill 名称冲突：${duplicateName}`
    if (duplicateSubagent) return `子智能体名称冲突：${duplicateSubagent}`
    if (tooManySubagents) return '一次最多挂载 5 个子智能体'
    if (tooManyMcps) return '一次最多挂载 3 个 MCP'
    if (tooMany) return '一次最多挂载 10 个 Skill'
    return null
  }

  // **配置持久化**：把本轮配置写回会话默认。会话级 agent_config 是下一次提问的
  // 继承来源，也决定 system prompt 是否稳定（对 kv cache 命中率有直接影响）。
  const persistThreadConfig = async (config: AgentConfig) => {
    if (!threadId) return
    try {
      await updateThread(threadId, { agent_config: config })
      await queryClient.invalidateQueries({ queryKey: threadKeys.detail(threadId) })
    } catch (error) {
      toast({ title: '会话配置保存失败', description: errorMessage(error), variant: 'error' })
    }
  }

  const finishConfig = () => {
    const error = combinedConfigError()
    if (error) {
      setConfigError(error)
      setActiveTab(errorTab())
      return
    }
    const config = buildRunAgentConfig(mode, prompt, agentId, skillIds, subagentIds, mcpIds)
    setConfigError('')
    // 立即关窗，持久化放后台 —— 失败有 toast，不挡用户继续输入
    setConfigOpen(false)
    if (config !== undefined) void persistThreadConfig(config)
  }

  const handleSend = async () => {
    const content = text.trim()
    if (!content || disabled || isRunning || isSending || !onSend) return
    const error = combinedConfigError()
    if (error) {
      setConfigError(error)
      setActiveTab(errorTab())
      setConfigOpen(true)
      return
    }
    setConfigError('')
    setIsSending(true)
    try {
      const config = buildRunAgentConfig(mode, prompt, agentId, skillIds, subagentIds, mcpIds)
      if (config !== undefined) await persistThreadConfig(config)
      await onSend(content, config)
      setText('')
    } catch {
      // mutation 状态负责显示错误；保留输入供用户修改或重试。
    } finally {
      setIsSending(false)
    }
  }

  const visibleAgentMode = mode === 'inherit' ? 'default' : mode
  const configSummary = mode === 'inherit'
    ? describeAgentConfig(threadAgentConfig, agents.data ?? [])
    : mode === 'agent'
      ? (selectedAgent ? `智能体：${selectedAgent.name}` : '选择一个智能体')
      : mode === 'custom' ? '自定义提示词' : '平台默认配置'
  const additionsSummary = [
    skillIds.length ? `${skillIds.length} 个 Skill` : '',
    subagentIds.length ? `${subagentIds.length} 个子智能体` : '',
    mountedMcpList.length ? `${mountedMcpList.length} 个 MCP` : '',
  ].filter(Boolean).join(' · ')

  // ── 配置面板：分页签，每类配置一页 ──
  type ConfigTabId = 'agent' | 'skill' | 'subagent' | 'mcp'
  const CONFIG_TABS: ReadonlyArray<{ id: ConfigTabId; label: string }> = [
    { id: 'agent', label: '智能体' },
    { id: 'skill', label: 'Skill' },
    { id: 'subagent', label: '子智能体' },
    { id: 'mcp', label: 'MCP' },
  ]
  const [activeTab, setActiveTab] = useState<ConfigTabId>('agent')
  const tabBadge = (id: ConfigTabId): number | null => {
    if (id === 'skill') return skillIds.length || null
    if (id === 'subagent') return subagentIds.length || null
    if (id === 'mcp') return mountedMcpList.length || null
    return null
  }
  // 校验不过时跳到出问题的那一页，错误当场可见
  const errorTab = (): ConfigTabId => {
    if (mode === 'custom' || mode === 'agent') return 'agent'
    if (duplicateName || tooMany) return 'skill'
    if (duplicateSubagent || tooManySubagents) return 'subagent'
    if (tooManyMcps) return 'mcp'
    return 'agent'
  }
  const onTabsKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    const index = CONFIG_TABS.findIndex(one => one.id === activeTab)
    const next = event.key === 'ArrowRight' ? (index + 1) % CONFIG_TABS.length
      : event.key === 'ArrowLeft' ? (index - 1 + CONFIG_TABS.length) % CONFIG_TABS.length
      : event.key === 'Home' ? 0
      : event.key === 'End' ? CONFIG_TABS.length - 1
      : -1
    if (next >= 0) {
      event.preventDefault()
      setActiveTab(CONFIG_TABS[next].id)
      document.getElementById(`config-tab-${CONFIG_TABS[next].id}`)?.focus()
    }
  }

  const skillItems: PickableItem[] = (skills.data ?? []).map(one => ({ id: one.id, name: one.name, meta: `${one.owner_name} · v${one.version}` }))
  const subagentItems: PickableItem[] = (subagents.data ?? []).map(one => ({ id: one.id, name: one.name, meta: `${one.owner_name} · v${one.version}` }))
  const mcpItems: PickableItem[] = (mcps.data ?? []).map(one => ({ id: one.id, name: one.name, meta: `${one.tool_names.length} 个工具 · 校外` }))

  return (
    <div className="chat-composer-area">
      <div className="composer">
        <textarea ref={textareaRef} className="composer-input" value={text} disabled={disabled || isSending} onChange={event => setText(event.target.value)} onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); void handleSend() } }} placeholder="输入分析需求…（Enter 发送，Shift+Enter 换行）" rows={1} />
        <div className="composer-footer">
          <button type="button" className="composer-config" aria-label="本轮智能体配置" aria-expanded={configOpen} onClick={() => setConfigOpen(open => !open)}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6"/></svg>
            <span className="composer-config-value">{configSummary}{additionsSummary ? ` · ${additionsSummary}` : ''}</span>
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><polyline points="18 15 12 9 6 15"/></svg>
          </button>
          <span className="composer-hint">Enter 发送 · Shift+Enter 换行</span>
          {isRunning ? (
            <button type="button" className="composer-stop" onClick={onStop} aria-label="停止分析" title="停止分析">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>
            </button>
          ) : (
            <button type="button" className="composer-send" disabled={disabled || isSending || !text.trim()} onClick={() => void handleSend()} aria-label="发送" title="发送">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden="true"><path d="M12 19V5M5 12l7-7 7 7"/></svg>
            </button>
          )}
        </div>
      </div>

      <Dialog.Root open={configOpen} onOpenChange={setConfigOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="dialog-overlay dialog-overlay-strong" />
          <Dialog.Content className="dialog-content dialog-content-config">
            <div className="config-header">
              <Dialog.Title className="dialog-title" style={{ marginBottom: 2 }}>本轮智能体配置</Dialog.Title>
              <Dialog.Description className="sr-only">分页签配置本轮使用的智能体、Skill、子智能体与 MCP，配置会保存为这个会话的默认。</Dialog.Description>
              <Dialog.Close asChild>
                <button type="button" aria-label="关闭配置" className="dialog-close-x">×</button>
              </Dialog.Close>
            </div>
            <div className="config-tabs" role="tablist" aria-label="配置分类" onKeyDown={onTabsKeyDown}>
              {CONFIG_TABS.map(one => (
                <button key={one.id} type="button" role="tab" id={`config-tab-${one.id}`} aria-selected={activeTab === one.id} aria-controls={`config-panel-${one.id}`} tabIndex={activeTab === one.id ? 0 : -1} className="config-tab" onClick={() => setActiveTab(one.id)}>
                  {one.label}
                  {tabBadge(one.id) !== null && <span className="config-tab-badge">{tabBadge(one.id)}</span>}
                </button>
              ))}
            </div>
            <div className="config-body">
              <div role="tabpanel" id="config-panel-agent" aria-labelledby="config-tab-agent" className="config-tabpanel" hidden={activeTab !== 'agent'}>
                <div className="config-role-heading">
                  <div className="config-role-title">角色来源</div>
                  <div className="config-role-description">保存后用于本轮及这个会话的后续分析</div>
                </div>
                <div className="config-modes" role="radiogroup" aria-label="角色来源">
                  {VISIBLE_AGENT_MODES.map(one => (
                    <label key={one.value} className="config-mode">
                      <input type="radio" name="agent-config-mode" className="config-mode-input" value={one.value} aria-label={one.ariaLabel} checked={visibleAgentMode === one.value} onChange={() => { setMode(one.value); setConfigError('') }} />
                      <span className="config-mode-pill">
                        <span className="config-mode-title">{one.label}</span>
                        <span className="config-mode-description">{one.description}</span>
                      </span>
                    </label>
                  ))}
                </div>
                {visibleAgentMode === 'default' && <div className="config-note">
                  使用平台基础分析角色；仍可在其他页签中挂载 Skill、子智能体或 MCP。
                </div>}
                {visibleAgentMode === 'agent' && <div className="config-field">
                  <label className="config-field-label" htmlFor="config-agent-select">选择智能体</label>
                  <select id="config-agent-select" className="config-select" aria-label="选择智能体" value={agentId} onChange={event => { setAgentId(event.target.value); setConfigError('') }}>
                    <option value="">-- 请选择 --</option>
                    {(agents.data ?? []).map(one => <option key={one.id} value={one.id}>{one.name}（{listingCaption(one)}）</option>)}
                  </select>
                  <div className="config-hint">
                    {agents.isPending && '正在加载可用的智能体…'}
                    {agents.isError && <span style={{ color: 'var(--danger)' }}>{errorMessage(agents.error)}</span>}
                    {!agents.isPending && !agents.isError && (agents.data ?? []).length === 0 && '还没有你能引用的智能体。去「智能体广场」看看，或自己建一个。'}
                    {!agents.isPending && (agents.data ?? []).length > 0 && '提交时会冻结智能体版本及它自带的 Skill。'}
                  </div>
                  {selectedAgent && (
                    <div className="config-agent-card">
                      <div className="config-agent-card-name">{selectedAgent.name} <span>v{selectedAgent.version} · {selectedAgent.owner_name} · {listingCaption(selectedAgent)}</span></div>
                      {selectedAgent.description && <div className="config-agent-card-desc">{selectedAgent.description}</div>}
                    </div>
                  )}
                </div>}
                {visibleAgentMode === 'custom' && <div className="config-field">
                  <label className="config-field-label" htmlFor="config-custom-prompt">自定义提示词</label>
                  <textarea id="config-custom-prompt" className="config-textarea" value={prompt} maxLength={MAX_SYSTEM_PROMPT_LENGTH} onChange={event => { setPrompt(event.target.value); setConfigError('') }} placeholder="例如：你是一名谨慎的金融风险分析师…" />
                  <div className="config-hint" style={{ textAlign: 'right' }}>{prompt.length} / {MAX_SYSTEM_PROMPT_LENGTH}</div>
                </div>}
              </div>

              <div role="tabpanel" id="config-panel-skill" aria-labelledby="config-tab-skill" className="config-tabpanel" hidden={activeTab !== 'skill'}>
                <ConfigPicker title="本轮 Skill（可多选，最多 10 个）" searchable={(skills.data ?? []).length > 6} empty={skills.isError ? errorMessage(skills.error) : '还没有你能使用的 Skill。'} items={skillItems} selectedIds={skillIds} onToggle={toggleSkill} />
                {mountedSkills.length > 0 && <div className="config-hint">最终挂载：{mountedSkills.join('、')}</div>}
              </div>

              <div role="tabpanel" id="config-panel-subagent" aria-labelledby="config-tab-subagent" className="config-tabpanel" hidden={activeTab !== 'subagent'}>
                <ConfigPicker title="本轮子智能体（可多选，最多 5 个）" searchable={(subagents.data ?? []).length > 6} empty={subagents.isError ? errorMessage(subagents.error) : '还没有可挂载的子智能体。'} items={subagentItems} selectedIds={subagentIds} onToggle={toggleSubagent} />
                {mountedSubagents.length > 0 && <div className="config-hint">最终挂载：{mountedSubagents.join('、')}</div>}
              </div>

              <div role="tabpanel" id="config-panel-mcp" aria-labelledby="config-tab-mcp" className="config-tabpanel" hidden={activeTab !== 'mcp'}>
                <ConfigPicker title="本轮 MCP（可多选，最多 3 个）" searchable={(mcps.data ?? []).length > 6} empty={mcps.isError ? errorMessage(mcps.error) : '还没有放行的 MCP。'} items={mcpItems} selectedIds={mcpIds} onToggle={toggleMcp} />
                {mountedMcpList.length > 0 && <div data-testid="mcp-outbound" className="config-warn">
                  <div>最终挂载：{mountedMcpList.map(one => one.via ? `${one.name}（来自 ${one.via}）` : one.name).join('、')}</div>
                </div>}
              </div>

              {configError && <div role="alert" className="config-error">{configError}</div>}
            </div>
            <div className="config-footer">
              <input className="config-scene-input" value={sceneName} onChange={event => setSceneName(event.target.value)} placeholder="场景名称（可选）" aria-label="场景名称" />
              <Button variant="outline" size="sm" onClick={() => saveScene.mutate()} disabled={saveScene.isPending}>{saveScene.isPending ? '保存中…' : '保存到我的场景库'}</Button>
              <div style={{ flex: 1 }} />
              <Button variant="primary" size="sm" onClick={() => void finishConfig()}>完成</Button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
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
