import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

type AgentType = 'prompt' | 'deployed'

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

export function CreateAgent() {
  const navigate = useNavigate()

  const [name, setName] = useState('')
  const [subject, setSubject] = useState('金融学')
  const [desc, setDesc] = useState('')
  const [agentType, setAgentType] = useState<AgentType | null>(null)
  const [prompt, setPrompt] = useState('')
  const [deployNote, setDeployNote] = useState('')

  const canSave = name.trim() && desc.trim() && agentType !== null &&
    (agentType === 'deployed' || prompt.trim())

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault()
    if (!canSave) return
    if (agentType === 'prompt') {
      navigate('/workspace/my-agents', { state: { toast: '智能体已创建，进入「已创建」状态' } })
    } else {
      navigate('/workspace/my-agents', { state: { toast: '申请已提交，后台团队将与你联系，智能体状态为「部署中」' } })
    }
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

        <form onSubmit={handleSave}>
          {/* 基本信息 */}
          <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, padding: 24, marginBottom: 16 }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 20 }}>基本信息</div>
            <FormField label="智能体名称" required>
              <input value={name} onChange={e => setName(e.target.value)} placeholder="如：企业财务异常检测" style={inputStyle} />
            </FormField>
            <FormField label="所属学科">
              <select value={subject} onChange={e => setSubject(e.target.value)} style={{ ...inputStyle, cursor: 'pointer' }}>
                {SUBJECT_OPTIONS.map(s => <option key={s}>{s}</option>)}
              </select>
            </FormField>
            <FormField label="功能描述" required hint="说明这个智能体能做什么，发布到广场时会作为卡片展示内容">
              <textarea
                value={desc}
                onChange={e => setDesc(e.target.value)}
                placeholder="简要描述分析场景与产出结果"
                style={{ ...inputStyle, minHeight: 80, resize: 'vertical' as const }}
                maxLength={200}
              />
            </FormField>
          </div>

          {/* 类型选择 */}
          <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, padding: 24, marginBottom: 16 }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 16 }}>智能体类型</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <TypeOption
                selected={agentType === 'prompt'}
                icon={<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>}
                title="Prompt 智能体"
                desc="通过系统提示词定义分析角色和步骤，无需代码，填写即可使用。"
                accentColor="var(--action)"
                onClick={() => setAgentType('prompt')}
              />
              <TypeOption
                selected={agentType === 'deployed'}
                icon={<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M22 2L11 13"/><path d="M22 2L15 22 11 13 2 9l20-7z"/></svg>}
                title="独立部署 Agent"
                desc="需要自定义工具或外部 API 接入，由后台团队协助部署。"
                accentColor="#7C3AED"
                onClick={() => setAgentType('deployed')}
              />
            </div>
          </div>

          {/* Prompt 配置（选了 prompt 才显示） */}
          {agentType === 'prompt' && (
            <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, padding: 24, marginBottom: 16 }}>
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
          )}

          {/* 独立部署联系信息（选了 deployed 才显示） */}
          {agentType === 'deployed' && (
            <div style={{ marginBottom: 16 }}>
              <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, overflow: 'hidden', marginBottom: 12 }}>
                <div style={{ padding: '12px 20px', background: 'var(--bg)', borderBottom: '1px solid var(--border)', fontSize: 11, fontFamily: "'JetBrains Mono', monospace", textTransform: 'uppercase' as const, letterSpacing: '0.2em', color: 'var(--text-muted)' }}>
                  // CONTACT · 请联系以下负责人协助部署
                </div>
                {CONTACT_INFO.map((c, i) => (
                  <div key={c.email} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '14px 20px', borderBottom: i < CONTACT_INFO.length - 1 ? '1px solid var(--border-light)' : 'none' }}>
                    <div>
                      <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 2 }}>{c.name}</div>
                      <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{c.role}</div>
                    </div>
                    <a href={`mailto:${c.email}`} style={{ fontSize: 13, color: 'var(--action)', textDecoration: 'none', fontFamily: "'JetBrains Mono', monospace" }}>
                      {c.email}
                    </a>
                  </div>
                ))}
              </div>
              {/* 给负责人带句话 */}
              <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, padding: '16px 20px', marginBottom: 12 }}>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 4 }}>
                  给负责人带句话
                </label>
                <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 10, lineHeight: 1.6 }}>
                  可以简要阐述 Agent 的技术栈和使用的工具，方便对接。
                </div>
                <textarea
                  value={deployNote}
                  onChange={e => setDeployNote(e.target.value)}
                  placeholder={'例如：该 Agent 基于 LangChain 实现，需要调用内部 Wind 数据接口和 PostgreSQL 数据库，预计输入财报 Excel，输出 JSON 格式的风险评分结果。'}
                  style={{ width: '100%', minHeight: 100, padding: '9px 12px', border: '1px solid var(--border)', borderRadius: 7, fontSize: 13, fontFamily: 'inherit', resize: 'vertical' as const, background: '#F7F9FC', outline: 'none', boxSizing: 'border-box' as const, color: 'var(--text-primary)', lineHeight: 1.7 }}
                  onFocus={e => (e.target.style.borderColor = 'var(--action)')}
                  onBlur={e => (e.target.style.borderColor = 'var(--border)')}
                />
              </div>
              <div style={{ background: '#FFFBEB', border: '1px solid #FDE68A', borderRadius: 8, padding: '10px 16px', fontSize: 13, color: '#92400E', lineHeight: 1.7 }}>
              <span style={{ display: 'inline-flex', alignItems: 'flex-start', gap: 8 }}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" style={{ flexShrink: 0, marginTop: 1 }}><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                点击「确认创建」后，智能体将以「部署中」状态保存至「我的智能体」，同时请联系以上负责人说明需求（功能描述、所需数据源或工具、预期输入输出格式）。负责人完成部署后会将状态更新为「已创建」，届时即可正常调用和发布。
              </span>
              </div>
            </div>
          )}

          {/* 操作按钮 */}
          <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
            <button
              type="button"
              onClick={() => navigate('/workspace/my-agents')}
              style={{ padding: '9px 20px', background: 'var(--surface)', color: 'var(--text-secondary)', border: '1px solid var(--border)', borderRadius: 7, fontSize: 13, cursor: 'pointer', fontFamily: 'inherit' }}
            >取消</button>
            <button
              type="submit"
              disabled={!canSave}
              style={{
                padding: '9px 20px',
                background: canSave ? (agentType === 'deployed' ? '#7C3AED' : 'var(--action)') : 'var(--text-muted)',
                color: '#fff', border: 'none', borderRadius: 7, fontSize: 13, fontWeight: 600,
                cursor: canSave ? 'pointer' : 'default', fontFamily: 'inherit',
              }}
            >
              {agentType === 'deployed' ? '确认创建' : '保存'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

function TypeOption({ selected, icon, title, desc, accentColor, onClick }: {
  selected: boolean; icon: React.ReactNode; title: string; desc: string; accentColor: string; onClick: () => void
}) {
  const [hovered, setHovered] = useState(false)
  const active = selected || hovered
  return (
    <button
      type="button"
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        background: selected ? (accentColor === 'var(--action)' ? 'var(--action-light)' : '#F5F3FF') : 'var(--surface)',
        border: `2px solid ${active ? accentColor : 'var(--border)'}`,
        borderRadius: 10, padding: '16px 18px',
        textAlign: 'left' as const, cursor: 'pointer', fontFamily: 'inherit',
        transition: 'border-color 0.15s, background 0.15s',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
        <span style={{ display: 'flex', alignItems: 'center', color: 'var(--text-secondary)' }}>{icon}</span>
        <span style={{ fontSize: 14, fontWeight: 700, color: active ? accentColor : 'var(--text-primary)' }}>{title}</span>
        {selected && (
          <span style={{ marginLeft: 'auto', fontSize: 11, fontWeight: 600, color: accentColor }}>✓ 已选择</span>
        )}
      </div>
      <div style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.6 }}>{desc}</div>
    </button>
  )
}
