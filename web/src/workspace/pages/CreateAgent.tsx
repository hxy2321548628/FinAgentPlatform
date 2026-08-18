import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { Bot, Boxes, Check, ChevronLeft, ChevronRight, FileText, Network, Save, Search, Wrench } from 'lucide-react'
import { agentKeys, createAgent, getMine, listSubagentCandidates, updateAgent, writeDraft } from '../../api/agents'
import { listCatalog as listMcpCatalog, mcpKeys } from '../../api/mcp'
import { errorMessage } from '../../api/request'
import { listAvailable as listAvailableSkills, skillKeys } from '../../api/skills'
import { Button } from '../../components/ui/Button'
import { MAX_SYSTEM_PROMPT_LENGTH, systemPromptError } from '../config'

const MAX_NAME_LENGTH = 32
const MAX_DESCRIPTION_LENGTH = 200
const PICKER_PAGE_SIZE = 6
const SUBJECTS = ['公司金融', '量化投资', '资产管理', '风险管理', '学术科研', '会计审计', '其他']

type BuilderStep = 'basics' | 'prompt' | 'capabilities' | 'orchestration'
type CapabilityTab = 'skills' | 'mcps'

const AGENT_STEPS: Array<{ id: BuilderStep; title: string; description: string }> = [
  { id: 'basics', title: '基本信息', description: '名称、说明与学科' },
  { id: 'prompt', title: '行为设定', description: '编写系统提示词' },
]

const SCENARIO_STEPS: Array<{ id: BuilderStep; title: string; description: string }> = [
  ...AGENT_STEPS,
  { id: 'capabilities', title: '能力组件', description: '组合 Skills 与 MCP' },
  { id: 'orchestration', title: '协作编排', description: '选择子智能体并检查' },
]

interface PickerItem {
  id: string
  title: string
  subtitle: string
  badge?: string
}

/** 建一个智能体，或改一个已有的；场景沿用同一份数据模型与编辑器。 */
export function CreateAgent() {
  const { agentId } = useParams()
  const navigate = useNavigate()
  const location = useLocation()
  const scenarioMode = location.pathname.includes('/my-scenarios')
  const noun = scenarioMode ? '场景' : '智能体'
  const steps = scenarioMode ? SCENARIO_STEPS : AGENT_STEPS
  const returnPath = scenarioMode ? '/workspace/my-scenarios' : '/workspace/my-agents'
  const queryClient = useQueryClient()
  const editing = Boolean(agentId)

  const availableSkills = useQuery({ queryKey: skillKeys.available(), queryFn: listAvailableSkills, enabled: scenarioMode })
  const availableSubagents = useQuery({ queryKey: agentKeys.subagentCandidates(), queryFn: listSubagentCandidates, enabled: scenarioMode })
  const availableMcps = useQuery({ queryKey: mcpKeys.catalog(), queryFn: listMcpCatalog, enabled: scenarioMode })
  const existing = useQuery({
    queryKey: agentKeys.detail(agentId ?? ''),
    queryFn: () => getMine(agentId ?? ''),
    enabled: editing,
  })

  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [subject, setSubject] = useState(SUBJECTS[0])
  const [prompt, setPrompt] = useState('')
  const [selectedSkillIds, setSelectedSkillIds] = useState<string[]>([])
  const [selectedSubagentIds, setSelectedSubagentIds] = useState<string[]>([])
  const [selectedMcpIds, setSelectedMcpIds] = useState<string[]>([])
  const [activeStep, setActiveStep] = useState<BuilderStep>('basics')
  const [capabilityTab, setCapabilityTab] = useState<CapabilityTab>('skills')
  const [skillSearch, setSkillSearch] = useState('')
  const [mcpSearch, setMcpSearch] = useState('')
  const [subagentSearch, setSubagentSearch] = useState('')
  const [error, setError] = useState('')
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    const agent = existing.data
    if (!agent || loaded) return
    setName(agent.name)
    setDescription(agent.description)
    setSubject(agent.subject || SUBJECTS[0])
    const draft = agent.versions.find(one => one.status === 'draft')
    const released = [...agent.versions].reverse().find(one => one.status === 'released')
    setPrompt(draft?.system_prompt ?? released?.system_prompt ?? '')
    setSelectedSkillIds(scenarioMode ? (draft?.skill_refs ?? released?.skill_refs ?? []).map(one => one.skill_id) : [])
    setSelectedSubagentIds(scenarioMode ? (draft?.subagent_refs ?? released?.subagent_refs ?? []).map(one => one.agent_id) : [])
    setSelectedMcpIds(scenarioMode ? (draft?.mcp_refs ?? released?.mcp_refs ?? []).map(one => one.server_id) : [])
    setLoaded(true)
  }, [existing.data, loaded, scenarioMode])

  const skillItems = useMemo<PickerItem[]>(() => (availableSkills.data ?? []).map(skill => ({
    id: skill.id,
    title: `${skill.name} · v${skill.version}`,
    subtitle: `${skill.owner_name} · ${skill.subject || '未分类'} · ${skill.description}`,
    badge: 'Skill',
  })), [availableSkills.data])
  const mcpItems = useMemo<PickerItem[]>(() => (availableMcps.data ?? []).map(server => ({
    id: server.id,
    title: server.name,
    subtitle: `${server.tool_names.join('、') || '未声明工具'} · ${server.description}`,
    badge: 'MCP',
  })), [availableMcps.data])
  const subagentItems = useMemo<PickerItem[]>(() => (availableSubagents.data ?? []).map(agent => ({
    id: agent.id,
    title: `${agent.name} · v${agent.version}`,
    subtitle: `${agent.owner_name} · ${agent.subject || '未分类'} · ${agent.description}`,
    badge: 'Agent',
  })), [availableSubagents.data])

  const save = useMutation({
    async mutationFn() {
      const skills = scenarioMode ? selectedSkillIds : []
      const subagents = scenarioMode ? selectedSubagentIds : []
      const mcps = scenarioMode ? selectedMcpIds : []
      if (!agentId) return createAgent({ name, description, subject, system_prompt: prompt, skills, subagents, mcps })
      await updateAgent(agentId, { name, description, subject })
      return writeDraft(agentId, prompt, skills, subagents, mcps)
    },
    async onSuccess() {
      await queryClient.invalidateQueries({ queryKey: agentKeys.all })
      navigate(returnPath)
    },
  })

  const validationStep = (): BuilderStep | null => {
    if (!name.trim()) {
      setError(`请填写${noun}名称`)
      return 'basics'
    }
    const promptError = systemPromptError(prompt)
    if (promptError) {
      setError(promptError)
      return 'prompt'
    }
    if (scenarioMode && selectedSubagentIds.length === 0) {
      setError('场景至少需要一个子智能体，请在“协作编排”中选择')
      return 'orchestration'
    }
    return null
  }

  const submit = (event: React.FormEvent) => {
    event.preventDefault()
    const invalidStep = validationStep()
    if (invalidStep) {
      setActiveStep(invalidStep)
      return
    }
    setError('')
    save.mutate()
  }

  const currentIndex = steps.findIndex(step => step.id === activeStep)
  const goStep = (step: BuilderStep) => {
    setActiveStep(step)
    setError('')
  }
  const toggle = (setter: React.Dispatch<React.SetStateAction<string[]>>, id: string) => setter(current => current.includes(id) ? current.filter(one => one !== id) : [...current, id])
  const completed: Record<BuilderStep, boolean> = {
    basics: Boolean(name.trim()),
    prompt: systemPromptError(prompt) === '',
    capabilities: true,
    orchestration: !scenarioMode || selectedSubagentIds.length > 0,
  }

  if (editing && existing.isPending) {
    return <div className="agent-builder-loading">正在加载…</div>
  }
  if (editing && existing.isError) {
    return <div role="alert" className="agent-builder-loading error">{errorMessage(existing.error)}</div>
  }

  return (
    <div className="agent-builder-page">
      <header className="agent-builder-header">
        <div>
          <div className="page-eyebrow">// {editing ? 'EDIT' : 'CREATE'} {scenarioMode ? 'SCENARIO' : 'AGENT'}</div>
          <h1 className="page-title">{editing ? `编辑${noun}` : `创建${noun}`}</h1>
          <p className="page-desc">{scenarioMode
            ? '分步完成基本信息、系统提示词、能力组件与协作编排，保存后生成仅自己可见的草稿。'
            : '智能体由基本信息与系统提示词定义，保存后生成仅自己可见的草稿。'}</p>
        </div>
        <Button variant="secondary" size="sm" onClick={() => navigate(returnPath)}>返回列表</Button>
      </header>

      <form className="agent-builder-form" onSubmit={submit}>
        <div className="agent-builder-workbench">
          <nav className="agent-builder-steps" aria-label={`${noun}配置步骤`}>
            <div className="agent-builder-steps-title">配置流程</div>
            {steps.map((step, index) => (
              <button key={step.id} type="button" className={`agent-builder-step${activeStep === step.id ? ' active' : ''}`} onClick={() => goStep(step.id)}>
                <span className={`agent-builder-step-index${completed[step.id] ? ' done' : ''}`}>{completed[step.id] ? <Check size={13} /> : index + 1}</span>
                <span><strong>{step.title}</strong><small>{step.description}</small></span>
              </button>
            ))}
            <div className="agent-builder-type-note">
              {scenarioMode ? <Network size={15} /> : <Bot size={15} />}
              <span>{scenarioMode
                ? '场景可组合 Skill、MCP 与子智能体，完成多角色协作。'
                : '智能体仅通过系统提示词定义角色、方法与输出。'}</span>
            </div>
          </nav>

          <main className={`agent-builder-canvas${activeStep === 'capabilities' || activeStep === 'orchestration' ? ' picker' : ''}`}>
            {activeStep === 'basics' && (
              <BuilderSection eyebrow="STEP 01" title={`${noun}的基本信息`} description="这些信息会出现在你的列表与公共目录卡片中。">
                <Field label={`${noun}名称`} required hint="保持清晰、具体，说明它负责解决什么问题。">
                  <input data-testid="agent-name" value={name} maxLength={MAX_NAME_LENGTH} onChange={event => { setName(event.target.value); setError('') }} placeholder={scenarioMode ? '如：企业信用风险联合研判' : '如：企业财务异常检测'} />
                  <FieldCounter current={name.length} max={MAX_NAME_LENGTH} />
                </Field>
                <Field label="一句话说明" hint="建议写清输入对象、分析方法和主要输出。">
                  <textarea value={description} maxLength={MAX_DESCRIPTION_LENGTH} onChange={event => setDescription(event.target.value)} placeholder="如：对财报关键科目做稽核式检查，输出带证据的异常项清单" rows={4} />
                  <FieldCounter current={description.length} max={MAX_DESCRIPTION_LENGTH} />
                </Field>
                <Field label="所属学科">
                  <select value={subject} onChange={event => setSubject(event.target.value)}>
                    {SUBJECTS.map(one => <option key={one} value={one}>{one}</option>)}
                  </select>
                </Field>
              </BuilderSection>
            )}

            {activeStep === 'prompt' && (
              <BuilderSection eyebrow="STEP 02" title="定义行为与边界" description="系统提示词决定分析风格、工作方法与输出标准；平台环境约束会自动附加。">
                <div className="agent-builder-prompt-guide">
                  <PromptGuide icon={<Bot size={16} />} title="角色" text="它是谁，擅长什么领域" />
                  <PromptGuide icon={<Wrench size={16} />} title="方法" text="分析步骤、工具与判断原则" />
                  <PromptGuide icon={<FileText size={16} />} title="输出" text="结构、证据与质量要求" />
                </div>
                <Field label="系统提示词" required hint="不要重复工作目录、产物目录、无公网等平台环境约束。">
                  <textarea data-testid="agent-system-prompt" className="agent-builder-prompt" value={prompt} maxLength={MAX_SYSTEM_PROMPT_LENGTH} onChange={event => { setPrompt(event.target.value); setError('') }} placeholder="你是一位严谨的金融分析师。先核对数据口径，再按以下步骤完成分析……" />
                  <FieldCounter current={prompt.length} max={MAX_SYSTEM_PROMPT_LENGTH} />
                </Field>
              </BuilderSection>
            )}

            {activeStep === 'capabilities' && (
              <BuilderSection picker eyebrow="STEP 03" title="组合能力组件" description="发布版本时会冻结所选 Skill 的版本；MCP 则引用管理员放行的服务目录。">
                <div className="agent-builder-tabs" role="tablist" aria-label="能力组件类型">
                  <button type="button" role="tab" aria-selected={capabilityTab === 'skills'} className={capabilityTab === 'skills' ? 'active' : ''} onClick={() => setCapabilityTab('skills')}><Boxes size={15} /> Skills <span>{selectedSkillIds.length}</span></button>
                  <button type="button" role="tab" aria-selected={capabilityTab === 'mcps'} className={capabilityTab === 'mcps' ? 'active' : ''} onClick={() => setCapabilityTab('mcps')}><Network size={15} /> MCP <span>{selectedMcpIds.length}</span></button>
                </div>
                {capabilityTab === 'skills' ? (
                  <CapabilityPicker label="Skill" items={skillItems} selectedIds={selectedSkillIds} onToggle={id => toggle(setSelectedSkillIds, id)} search={skillSearch} onSearch={setSkillSearch} placeholder="搜索 Skill 名称、作者或说明" loading={availableSkills.isPending} error={availableSkills.isError ? errorMessage(availableSkills.error) : ''} empty="当前没有可用 Skill。" />
                ) : (
                  <CapabilityPicker label="MCP" items={mcpItems} selectedIds={selectedMcpIds} onToggle={id => toggle(setSelectedMcpIds, id)} search={mcpSearch} onSearch={setMcpSearch} placeholder="搜索 MCP 名称、工具或说明" loading={availableMcps.isPending} error={availableMcps.isError ? errorMessage(availableMcps.error) : ''} empty="还没有管理员放行的 MCP。" />
                )}
              </BuilderSection>
            )}

            {activeStep === 'orchestration' && (
              <BuilderSection picker eyebrow="STEP 04" title="协作编排" description={scenarioMode ? '至少选择一个子智能体，组成可以分工协作的分析场景。' : '仅当它需要协调其他专家角色时选择；选择后会被归类为场景。'}>
                <CapabilityPicker label="子智能体" items={subagentItems} selectedIds={selectedSubagentIds} onToggle={id => { toggle(setSelectedSubagentIds, id); setError('') }} search={subagentSearch} onSearch={setSubagentSearch} placeholder="搜索子智能体名称、作者或说明" loading={availableSubagents.isPending} error={availableSubagents.isError ? errorMessage(availableSubagents.error) : ''} empty="当前没有可用子智能体。" />
              </BuilderSection>
            )}
          </main>

          <aside className="agent-builder-summary">
            <div className="agent-builder-summary-title">配置摘要</div>
            <div className="agent-builder-summary-name"><span>{scenarioMode ? 'SCENARIO' : 'AGENT'}</span><strong>{name.trim() || `未命名${noun}`}</strong><small>{subject}</small></div>
            <SummaryRow label="系统提示词" value={prompt.trim() ? `${prompt.length} 字` : '未填写'} ready={Boolean(prompt.trim())} />
            {scenarioMode && <SummaryRow label="Skills" value={`${selectedSkillIds.length} 个`} ready />}
            {scenarioMode && <SummaryRow label="MCP" value={`${selectedMcpIds.length} 个`} ready />}
            {scenarioMode && <SummaryRow label="子智能体" value={`${selectedSubagentIds.length} 个`} ready={selectedSubagentIds.length > 0} />}
            <div className="agent-builder-summary-divider" />
            <p>{editing ? '保存会更新元信息，并写入当前草稿版本。' : '创建后先进入草稿状态；发布、共享与提审在列表页完成。'}</p>
          </aside>
        </div>

        <footer className="agent-builder-footer">
          <div className="agent-builder-footer-message">
            {(error || save.isError) && <span role="alert">{error || errorMessage(save.error)}</span>}
            {!error && !save.isError && <span>第 {currentIndex + 1} / {steps.length} 步 · {steps[currentIndex].title}</span>}
          </div>
          <div className="agent-builder-footer-actions">
            <Button variant="secondary" size="sm" disabled={currentIndex === 0} onClick={() => goStep(steps[currentIndex - 1].id)}><ChevronLeft size={14} /> 上一步</Button>
            {currentIndex < steps.length - 1 && <Button variant="secondary" size="sm" onClick={() => goStep(steps[currentIndex + 1].id)}>下一步 <ChevronRight size={14} /></Button>}
            <Button variant="primary" size="sm" type="submit" disabled={save.isPending}><Save size={14} /> {save.isPending ? '正在保存…' : editing ? '保存草稿' : '创建草稿'}</Button>
          </div>
        </footer>
      </form>
    </div>
  )
}

function BuilderSection({ eyebrow, title, description, picker = false, children }: { eyebrow: string; title: string; description: string; picker?: boolean; children: React.ReactNode }) {
  return <section className={`agent-builder-section${picker ? ' picker' : ''}`}><div className="agent-builder-section-head"><span>{eyebrow}</span><h2>{title}</h2><p>{description}</p></div>{children}</section>
}

function Field({ label, required, hint, children }: { label: string; required?: boolean; hint?: string; children: React.ReactNode }) {
  return <div className="agent-builder-field"><label>{label}{required && <span>*</span>}</label>{hint && <p>{hint}</p>}{children}</div>
}

function FieldCounter({ current, max }: { current: number; max: number }) {
  return <div className="agent-builder-counter">{current} / {max}</div>
}

function PromptGuide({ icon, title, text }: { icon: React.ReactNode; title: string; text: string }) {
  return <div>{icon}<span><strong>{title}</strong><small>{text}</small></span></div>
}

function CapabilityPicker({ label, items, selectedIds, onToggle, search, onSearch, placeholder, loading, error, empty }: {
  label: string
  items: PickerItem[]
  selectedIds: string[]
  onToggle: (id: string) => void
  search: string
  onSearch: (value: string) => void
  placeholder: string
  loading: boolean
  error: string
  empty: string
}) {
  const [requestedPage, setRequestedPage] = useState(1)
  const normalized = search.trim().toLocaleLowerCase('zh-CN')
  const filtered = items.filter(item => `${item.title} ${item.subtitle}`.toLocaleLowerCase('zh-CN').includes(normalized))
  const totalPages = Math.max(1, Math.ceil(filtered.length / PICKER_PAGE_SIZE))
  const page = Math.min(requestedPage, totalPages)
  const start = (page - 1) * PICKER_PAGE_SIZE
  const visible = filtered.slice(start, start + PICKER_PAGE_SIZE)
  const updateSearch = (value: string) => {
    setRequestedPage(1)
    onSearch(value)
  }
  return (
    <div className="agent-builder-picker">
      <div className="agent-builder-picker-toolbar">
        <label className="agent-builder-search"><Search size={15} /><input aria-label={placeholder} value={search} onChange={event => updateSearch(event.target.value)} placeholder={placeholder} /></label>
        <div className="agent-builder-picker-selected" aria-live="polite"><Check size={14} /><strong>{selectedIds.length}</strong><span>已选</span></div>
      </div>
      <div className="agent-builder-picker-meta">
        <span>可用 {items.length} 项{normalized && ` · 匹配 ${filtered.length} 项`}</span>
        {!loading && !error && filtered.length > 0 && <span>每页最多 {PICKER_PAGE_SIZE} 项</span>}
      </div>
      {loading && <div role="status" className="agent-builder-picker-state">正在加载…</div>}
      {error && <div role="alert" className="agent-builder-picker-state error">{error}</div>}
      {!loading && !error && filtered.length === 0 && <div role="status" className="agent-builder-picker-state">{normalized ? '没有匹配项。' : empty}</div>}
      {!loading && !error && visible.length > 0 && <div className="agent-builder-picker-list" role="group" aria-label={`${label} 可选项`}>
        {visible.map(item => {
          const selected = selectedIds.includes(item.id)
          return (
            <label key={item.id} className={`agent-builder-picker-item${selected ? ' selected' : ''}`}>
              <input type="checkbox" checked={selected} onChange={() => onToggle(item.id)} aria-label={item.title} />
              <span className="agent-builder-picker-check">{selected && <Check size={13} />}</span>
              <span className="agent-builder-picker-copy"><strong title={item.title}>{item.title}</strong><small title={item.subtitle}>{item.subtitle}</small></span>
              {item.badge && <span className="agent-builder-picker-badge">{item.badge}</span>}
            </label>
          )
        })}
      </div>}
      {!loading && !error && filtered.length > 0 && (
        <div className="agent-builder-picker-pagination">
          <span>显示 {start + 1}–{Math.min(start + PICKER_PAGE_SIZE, filtered.length)} / {filtered.length}</span>
          {totalPages > 1 && (
            <nav aria-label={`${label} 分页`}>
              <button type="button" aria-label={`${label} 上一页`} disabled={page === 1} onClick={() => setRequestedPage(current => Math.max(1, current - 1))}><ChevronLeft size={14} /></button>
              <strong>第 {page} / {totalPages} 页</strong>
              <button type="button" aria-label={`${label} 下一页`} disabled={page === totalPages} onClick={() => setRequestedPage(current => Math.min(totalPages, current + 1))}><ChevronRight size={14} /></button>
            </nav>
          )}
        </div>
      )}
    </div>
  )
}

function SummaryRow({ label, value, ready }: { label: string; value: string; ready: boolean }) {
  return <div className="agent-builder-summary-row"><span className={ready ? 'ready' : ''}>{ready ? <Check size={11} /> : '!'}</span><strong>{label}</strong><small>{value}</small></div>
}
