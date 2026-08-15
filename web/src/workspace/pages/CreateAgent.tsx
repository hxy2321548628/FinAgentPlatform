import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useParams } from 'react-router-dom'
import { agentKeys, createAgent, getMine, updateAgent, writeDraft } from '../../api/agents'
import { errorMessage } from '../../api/request'
import { listAvailable as listAvailableSkills, skillKeys } from '../../api/skills'
import { MAX_SYSTEM_PROMPT_LENGTH, systemPromptError } from '../config'

const MAX_NAME_LENGTH = 32
const MAX_DESCRIPTION_LENGTH = 200
const SUBJECTS = ['公司金融', '量化投资', '资产管理', '风险管理', '学术科研', '会计审计', '其他']

/**
 * 建一个智能体，或改一个已有的。
 *
 * Agent 的内容由系统提示词与可选 Skill 引用组成；子智能体与 MCP 留给后续阶段。
 *
 * **改内容与改元信息是两条路**：改名不产生新版本，改提示词会（已经定稿的话，
 * 这一下追加下一个版本号的新草稿）。两者分开写在这里，因为它们打的是两个端点。
 */
export function CreateAgent() {
  const { agentId } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const editing = Boolean(agentId)

  const availableSkills = useQuery({ queryKey: skillKeys.available(), queryFn: listAvailableSkills })

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
  const [error, setError] = useState('')
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    const agent = existing.data
    if (!agent || loaded) return
    setName(agent.name)
    setDescription(agent.description)
    setSubject(agent.subject || SUBJECTS[0])
    // 编辑框里放的是**草稿**；没有草稿时回落到最新已发布版，
    // 保存时那一下会追加下一个版本号的新草稿
    const draft = agent.versions.find(one => one.status === 'draft')
    const released = [...agent.versions].reverse().find(one => one.status === 'released')
    setPrompt(draft?.system_prompt ?? released?.system_prompt ?? '')
    const refs = draft?.skill_refs ?? released?.skill_refs ?? []
    setSelectedSkillIds(refs.map(one => one.skill_id))
    setLoaded(true)
  }, [existing.data, loaded])

  const save = useMutation({
    async mutationFn() {
      if (!agentId) return createAgent({ name, description, subject, system_prompt: prompt, skills: selectedSkillIds })
      await updateAgent(agentId, { name, description, subject })
      return writeDraft(agentId, prompt, selectedSkillIds)
    },
    async onSuccess() {
      await queryClient.invalidateQueries({ queryKey: agentKeys.all })
      navigate('/workspace/my-agents')
    },
  })

  const submit = (event: React.FormEvent) => {
    event.preventDefault()
    if (!name.trim()) {
      setError('请填写智能体名称')
      return
    }
    const promptError = systemPromptError(prompt)
    if (promptError) {
      setError(promptError)
      return
    }
    setError('')
    save.mutate()
  }

  if (editing && existing.isPending) {
    return <div style={{ flex: 1, display: 'grid', placeItems: 'center', color: 'var(--text-muted)' }}>正在加载…</div>
  }
  if (editing && existing.isError) {
    return <div role="alert" style={{ flex: 1, padding: 36, color: '#DC2626' }}>{errorMessage(existing.error)}</div>
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '32px 36px', background: 'var(--bg)' }}>
      <div style={{ maxWidth: 680, margin: '0 auto' }}>
        <div style={{ marginBottom: 28 }}>
          <div style={{ fontSize: 10, fontFamily: "'JetBrains Mono', monospace", textTransform: 'uppercase', letterSpacing: '0.3em', color: 'var(--text-muted)', marginBottom: 6 }}>// {editing ? 'EDIT AGENT' : 'CREATE AGENT'}</div>
          <h1 style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>{editing ? '编辑智能体' : '创建智能体'}</h1>
          <p style={{ fontSize: 13, color: 'var(--text-muted)', lineHeight: 1.6 }}>
            智能体的内容就是一段提示词。保存之后它先是草稿，只有自己看得到；发布一版之后才谈得上共享与提审。
          </p>
        </div>

        <form onSubmit={submit}>
          <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, padding: 24, marginBottom: 20 }}>
            <Field label="名称" required hint="同一个作者名下不能重名。广场上重名靠作者名区分">
              <input value={name} maxLength={MAX_NAME_LENGTH} onChange={event => { setName(event.target.value); setError('') }} placeholder="如：企业财务异常检测" style={inputStyle} />
            </Field>
            <Field label="一句话说明" hint="广场卡片上展示的那两行">
              <textarea value={description} maxLength={MAX_DESCRIPTION_LENGTH} onChange={event => setDescription(event.target.value)} placeholder="如：对财报关键科目做稽核式比率检查，输出带证据的异常项清单" style={{ ...inputStyle, minHeight: 72, resize: 'vertical' }} />
            </Field>
            <Field label="学科">
              <select value={subject} onChange={event => setSubject(event.target.value)} style={{ ...inputStyle, cursor: 'pointer' }}>
                {SUBJECTS.map(one => <option key={one} value={one}>{one}</option>)}
              </select>
            </Field>
          </div>

          <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, padding: 24, marginBottom: 24 }}>
            <Field label="系统提示词" required hint="这段文字会替换平台默认的角色段。平台的环境契约（工作目录、产物目录、无公网）仍然会自动附在后面">
              <textarea
                value={prompt}
                maxLength={MAX_SYSTEM_PROMPT_LENGTH}
                onChange={event => { setPrompt(event.target.value); setError('') }}
                placeholder="如：你是一位专业的财务分析师，擅长识别财务报表中的异常信号…"
                style={{ ...inputStyle, minHeight: 220, resize: 'vertical', lineHeight: 1.7, fontFamily: "'JetBrains Mono', monospace" }}
              />
            </Field>
            <div style={{ textAlign: 'right', fontSize: 11, color: 'var(--text-muted)' }}>{prompt.length} / {MAX_SYSTEM_PROMPT_LENGTH}</div>
          </div>

          <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, padding: 24, marginBottom: 24 }}>
            <Field label="自带 Skills" hint="发布版本时会冻结所选 Skill 的当前版本；运行时还可以再临时追加">
              {availableSkills.isPending && <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>正在加载可用 Skills…</div>}
              {availableSkills.isError && <div role="alert" style={{ fontSize: 13, color: '#DC2626' }}>{errorMessage(availableSkills.error)}</div>}
              {!availableSkills.isPending && (availableSkills.data ?? []).length === 0 && <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>当前没有可用 Skill。</div>}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {(availableSkills.data ?? []).map(skill => (
                  <label key={skill.id} style={{ display: 'flex', alignItems: 'flex-start', gap: 9, padding: '9px 11px', border: '1px solid var(--border)', borderRadius: 7, cursor: 'pointer' }}>
                    <input
                      type="checkbox"
                      checked={selectedSkillIds.includes(skill.id)}
                      onChange={event => setSelectedSkillIds(current => event.target.checked ? [...current, skill.id] : current.filter(one => one !== skill.id))}
                      style={{ marginTop: 3 }}
                    />
                    <span style={{ minWidth: 0 }}>
                      <span style={{ display: 'block', fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>{skill.name} · v{skill.version}</span>
                      <span style={{ display: 'block', marginTop: 3, fontSize: 12, color: 'var(--text-muted)' }}>{skill.owner_name} · {skill.subject || '未分类'} · {skill.description}</span>
                    </span>
                  </label>
                ))}
              </div>
            </Field>
          </div>

          {(error || save.isError) && (
            <div role="alert" style={{ marginBottom: 16, padding: '9px 14px', background: '#FEF2F2', border: '1px solid #FECACA', borderRadius: 7, color: '#DC2626', fontSize: 13 }}>
              {error || errorMessage(save.error)}
            </div>
          )}

          <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
            <button type="button" onClick={() => navigate('/workspace/my-agents')} style={{ padding: '9px 20px', background: 'var(--surface)', color: 'var(--text-secondary)', border: '1px solid var(--border)', borderRadius: 7, fontSize: 13, cursor: 'pointer', fontFamily: 'inherit' }}>取消</button>
            <button type="submit" disabled={save.isPending} style={{ padding: '9px 20px', background: 'var(--action)', color: '#fff', border: 'none', borderRadius: 7, fontSize: 13, fontWeight: 600, cursor: save.isPending ? 'default' : 'pointer', opacity: save.isPending ? 0.6 : 1, fontFamily: 'inherit' }}>
              {save.isPending ? '正在保存…' : editing ? '保存草稿' : '创建'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

function Field({ label, required, hint, children }: { label: string; required?: boolean; hint?: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 18 }}>
      <label style={{ display: 'block', fontSize: 13, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 6 }}>
        {label}{required && <span style={{ color: '#DC2626', marginLeft: 3 }}>*</span>}
      </label>
      {hint && <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 6 }}>{hint}</div>}
      {children}
    </div>
  )
}

const inputStyle: React.CSSProperties = {
  width: '100%', padding: '9px 12px', border: '1px solid var(--border)', borderRadius: 7,
  fontSize: 13, color: 'var(--text-primary)', background: '#F7F9FC', outline: 'none',
  fontFamily: 'inherit', boxSizing: 'border-box',
}
