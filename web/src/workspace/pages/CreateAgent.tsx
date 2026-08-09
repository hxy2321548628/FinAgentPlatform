import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

type AgentType = 'prompt' | 'deployed'
// step 1: 填基本信息  step 2: 选类型  step 3: 对应配置（prompt填提示词 / deployed看联系方式）
type Step = 'info' | 'type' | 'prompt-config' | 'deployed-contact' | 'done'

const SUBJECT_OPTIONS = ['金融学', '会计学', '经济学', '管理科学', '其他']

const CONTACT_INFO = [
  { name: '辜老师', email: 'gu.teacher@fin.edu.cn', role: '平台技术负责人' },
  { name: '张同学', email: 'zhang.dev@fin.edu.cn', role: '后台开发' },
]

function FormField({ label, required, hint, children }: {
  label: string; required?: boolean; hint?: string; children: React.ReactNode
}) {
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
  width: '100%', padding: '9px 12px',
  border: '1px solid var(--border)', borderRadius: 7,
  fontSize: 13, color: 'var(--text-primary)',
  background: '#F7F9FC', outline: 'none',
  fontFamily: 'inherit', boxSizing: 'border-box',
}

// 步骤指示器
function StepBar({ current }: { current: Step }) {
  const steps = [
    { key: 'info',   label: '基本信息' },
    { key: 'type',   label: '选择类型' },
    { key: 'config', label: '配置详情' },
  ]
  const activeIdx = current === 'info' ? 0 : current === 'type' ? 1 : 2
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 0, marginBottom: 32 }}>
      {steps.map((s, i) => (
        <div key={s.key} style={{ display: 'flex', alignItems: 'center', flex: i < steps.length - 1 ? 1 : 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{
              width: 26, height: 26, borderRadius: '50%', flexShrink: 0,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 12, fontWeight: 700,
              background: i <= activeIdx ? 'var(--action)' : 'var(--border-light)',
              color: i <= activeIdx ? '#fff' : 'var(--text-muted)',
            }}>{i + 1}</div>
            <span style={{ fontSize: 13, fontWeight: i === activeIdx ? 600 : 400, color: i <= activeIdx ? 'var(--text-primary)' : 'var(--text-muted)', whiteSpace: 'nowrap' }}>{s.label}</span>
          </div>
          {i < steps.length - 1 && (
            <div style={{ flex: 1, height: 1, background: i < activeIdx ? 'var(--action)' : 'var(--border)', margin: '0 12px' }} />
          )}
        </div>
      ))}
    </div>
  )
}

export function CreateAgent() {
  const navigate = useNavigate()
  const [step, setStep] = useState<Step>('info')
  const [agentType, setAgentType] = useState<AgentType | null>(null)

  // 基本信息
  const [name, setName] = useState('')
  const [subject, setSubject] = useState('金融学')
  const [desc, setDesc] = useState('')

  // Prompt 配置
  const [prompt, setPrompt] = useState('')

  const handleInfoNext = (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim() || !desc.trim()) return
    setStep('type')
  }

  const handleTypeSelect = (type: AgentType) => {
    setAgentType(type)
    setStep(type === 'prompt' ? 'prompt-config' : 'deployed-contact')
  }

  const handlePromptSave = (e: React.FormEvent) => {
    e.preventDefault()
    if (!prompt.trim()) return
    setStep('done')
    setTimeout(() => navigate('/workspace/my-agents'), 1200)
  }

  const handleDeployedCreate = () => {
    // 独立部署：填完联系信息后创建，状态为"部署中"
    setStep('done')
    setTimeout(() => navigate('/workspace/my-agents'), 1200)
  }

  // 完成状态
  if (step === 'done') {
    const isDeploy = agentType === 'deployed'
    return (
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--bg)' }}>
        <div style={{ textAlign: 'center' as const }}>
          <div style={{ fontSize: 40, marginBottom: 16 }}>{isDeploy ? '🚀' : '✓'}</div>
          <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 8 }}>
            {isDeploy ? '申请已提交' : '创建成功'}
          </div>
          <div style={{ fontSize: 14, color: 'var(--text-muted)' }}>
            {isDeploy ? '后台团队将与你联系，智能体状态为「部署中」' : '智能体已保存至「已创建」，跳转中...'}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '32px 36px', background: 'var(--bg)' }}>
      <div style={{ maxWidth: 680, margin: '0 auto' }}>
        {/* 页头 */}
        <div style={{ marginBottom: 28 }}>
          <div style={{ fontSize: 10, fontFamily: "'JetBrains Mono', monospace", textTransform: 'uppercase' as const, letterSpacing: '0.3em', color: 'var(--text-muted)', marginBottom: 6 }}>// CREATE AGENT</div>
          <h1 style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>创建智能体</h1>
          <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>创建后进入「已创建」状态，可直接在对话中调用，或申请发布到广场。</p>
        </div>

        <StepBar current={step} />

        {/* ── Step 1: 基本信息 ── */}
        {step === 'info' && (
          <form onSubmit={handleInfoNext}>
            <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, padding: 24, marginBottom: 24 }}>
              <FormField label="智能体名称" required>
                <input value={name} onChange={e => setName(e.target.value)} placeholder="如：企业财务异常检测" style={inputStyle} />
              </FormField>
              <FormField label="所属学科">
                <select value={subject} onChange={e => setSubject(e.target.value)} style={{ ...inputStyle, cursor: 'pointer' }}>
                  {SUBJECT_OPTIONS.map(s => <option key={s}>{s}</option>)}
                </select>
              </FormField>
              <FormField label="功能描述" required hint="说明这个智能体能做什么，发布到广场时会作为卡片展示内容">
                <textarea value={desc} onChange={e => setDesc(e.target.value)} placeholder="简要描述分析场景与产出结果" style={{ ...inputStyle, minHeight: 90, resize: 'vertical' as const }} maxLength={200} />
              </FormField>
            </div>
            <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
              <button type="button" onClick={() => navigate('/workspace/my-agents')} style={{ padding: '9px 20px', background: 'var(--surface)', color: 'var(--text-secondary)', border: '1px solid var(--border)', borderRadius: 7, fontSize: 13, cursor: 'pointer', fontFamily: 'inherit' }}>取消</button>
              <button type="submit" style={{ padding: '9px 20px', background: 'var(--action)', color: '#fff', border: 'none', borderRadius: 7, fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>下一步</button>
            </div>
          </form>
        )}

        {/* ── Step 2: 选择类型 ── */}
        {step === 'type' && (
          <div>
            {/* 已填信息摘要 */}
            <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8, padding: '12px 16px', marginBottom: 20, display: 'flex', alignItems: 'center', gap: 12, fontSize: 13 }}>
              <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{name}</span>
              <span style={{ color: 'var(--border)' }}>·</span>
              <span style={{ color: 'var(--text-muted)' }}>{subject}</span>
              <button onClick={() => setStep('info')} style={{ marginLeft: 'auto', background: 'none', border: 'none', color: 'var(--action)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit' }}>修改</button>
            </div>

            <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 16 }}>选择智能体类型</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
              {/* Prompt 智能体 */}
              <TypeCard
                icon="💬"
                title="Prompt 智能体"
                desc="通过编写系统提示词定义智能体的分析角色、步骤和输出格式。无需代码，填写即可使用。"
                hint="适合：分析流程固定、逻辑清晰的场景"
                accentColor="var(--action)"
                onClick={() => handleTypeSelect('prompt')}
              />
              {/* 独立部署 */}
              <TypeCard
                icon="🚀"
                title="独立部署 Agent"
                desc="需要自定义工具、外部 API 接入或复杂工作流的 Agent，由平台后台团队协助部署。"
                hint="适合：需要调用特定数据源或工具的复杂场景"
                accentColor="#7C3AED"
                onClick={() => handleTypeSelect('deployed')}
              />
            </div>
            <div style={{ marginTop: 20, textAlign: 'right' as const }}>
              <button onClick={() => setStep('info')} style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: 13, fontFamily: 'inherit' }}>← 上一步</button>
            </div>
          </div>
        )}

        {/* ── Step 3a: Prompt 配置 ── */}
        {step === 'prompt-config' && (
          <form onSubmit={handlePromptSave}>
            {/* 摘要 */}
            <InfoSummary name={name} subject={subject} type="Prompt 智能体" onEdit={() => setStep('info')} onTypeEdit={() => setStep('type')} />
            <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, padding: 24, marginBottom: 24 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 4 }}>系统提示词</div>
              <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 16, lineHeight: 1.6 }}>
                这段文字作为 AI 的「工作说明」，决定智能体的分析角色、步骤和输出格式。写得越具体，结果越稳定。
              </div>
              <FormField label="提示词内容" required>
                <textarea
                  value={prompt}
                  onChange={e => setPrompt(e.target.value)}
                  placeholder={'你是一位专业的财务分析师。\n\n请按以下步骤完成分析：\n1. 读取数据，了解字段结构\n2. 计算关键财务指标（流动比率、ROE…）\n3. 识别异常项，输出带证据的清单\n4. 给出综合评估结论'}
                  style={{ ...inputStyle, minHeight: 220, resize: 'vertical' as const, fontFamily: "'JetBrains Mono', monospace", fontSize: 12, lineHeight: 1.75 }}
                />
              </FormField>
            </div>
            <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
              <button type="button" onClick={() => setStep('type')} style={{ padding: '9px 20px', background: 'var(--surface)', color: 'var(--text-secondary)', border: '1px solid var(--border)', borderRadius: 7, fontSize: 13, cursor: 'pointer', fontFamily: 'inherit' }}>← 上一步</button>
              <button type="submit" style={{ padding: '9px 20px', background: 'var(--action)', color: '#fff', border: 'none', borderRadius: 7, fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>创建智能体</button>
            </div>
          </form>
        )}

        {/* ── Step 3b: 独立部署联系信息 ── */}
        {step === 'deployed-contact' && (
          <div>
            <InfoSummary name={name} subject={subject} type="独立部署 Agent" onEdit={() => setStep('info')} onTypeEdit={() => setStep('type')} />
            <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, overflow: 'hidden', marginBottom: 16 }}>
              <div style={{ padding: '14px 20px', background: 'var(--bg)', borderBottom: '1px solid var(--border)', fontSize: 11, fontFamily: "'JetBrains Mono', monospace", textTransform: 'uppercase' as const, letterSpacing: '0.2em', color: 'var(--text-muted)' }}>
                // CONTACT · 请联系以下负责人协助部署
              </div>
              {CONTACT_INFO.map((c, i) => (
                <div key={c.email} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '16px 20px', borderBottom: i < CONTACT_INFO.length - 1 ? '1px solid var(--border-light)' : 'none' }}>
                  <div>
                    <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 3 }}>{c.name}</div>
                    <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{c.role}</div>
                  </div>
                  <a href={`mailto:${c.email}`} style={{ fontSize: 13, color: 'var(--action)', textDecoration: 'none', fontFamily: "'JetBrains Mono', monospace" }}>
                    {c.email}
                  </a>
                </div>
              ))}
            </div>
            <div style={{ background: '#FFFBEB', border: '1px solid #FDE68A', borderRadius: 8, padding: '12px 16px', fontSize: 13, color: '#92400E', lineHeight: 1.7, marginBottom: 24 }}>
              💡 联系时请说明：智能体的功能需求、需要接入的外部数据源或工具、预期的输入输出格式。联系后点击「确认创建」，智能体将以「部署中」状态保存至「我的智能体」。
            </div>
            <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
              <button onClick={() => setStep('type')} style={{ padding: '9px 20px', background: 'var(--surface)', color: 'var(--text-secondary)', border: '1px solid var(--border)', borderRadius: 7, fontSize: 13, cursor: 'pointer', fontFamily: 'inherit' }}>← 上一步</button>
              <button onClick={handleDeployedCreate} style={{ padding: '9px 20px', background: '#7C3AED', color: '#fff', border: 'none', borderRadius: 7, fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>确认创建</button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ── 子组件 ────────────────────────────────────────────

function TypeCard({ icon, title, desc, hint, accentColor, onClick }: {
  icon: string; title: string; desc: string; hint: string; accentColor: string; onClick: () => void
}) {
  const [hovered, setHovered] = useState(false)
  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        background: 'var(--surface)',
        border: `2px solid ${hovered ? accentColor : 'var(--border)'}`,
        borderRadius: 12, padding: '24px 20px',
        textAlign: 'left' as const, cursor: 'pointer', fontFamily: 'inherit',
        boxShadow: hovered ? `0 4px 16px ${accentColor}18` : 'none',
        transition: 'border-color 0.2s, box-shadow 0.2s',
      }}
    >
      <div style={{ fontSize: 28, marginBottom: 12 }}>{icon}</div>
      <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 8 }}>{title}</div>
      <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.65, marginBottom: 12 }}>{desc}</div>
      <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{hint}</div>
    </button>
  )
}

function InfoSummary({ name, subject, type, onEdit, onTypeEdit }: {
  name: string; subject: string; type: string; onEdit: () => void; onTypeEdit: () => void
}) {
  return (
    <div style={{ background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 8, padding: '12px 16px', marginBottom: 20, display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, flexWrap: 'wrap' as const }}>
      <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{name}</span>
      <span style={{ color: 'var(--border)' }}>·</span>
      <span style={{ color: 'var(--text-muted)' }}>{subject}</span>
      <span style={{ color: 'var(--border)' }}>·</span>
      <span style={{ color: 'var(--text-muted)' }}>{type}</span>
      <div style={{ marginLeft: 'auto', display: 'flex', gap: 10 }}>
        <button onClick={onEdit} style={{ background: 'none', border: 'none', color: 'var(--action)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit' }}>修改信息</button>
        <button onClick={onTypeEdit} style={{ background: 'none', border: 'none', color: 'var(--action)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit' }}>修改类型</button>
      </div>
    </div>
  )
}
