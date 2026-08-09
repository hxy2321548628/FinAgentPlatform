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
  transition: 'border-color 0.15s',
}

export function CreateAgent() {
  const navigate = useNavigate()
  const [agentType, setAgentType] = useState<AgentType | null>(null)
  const [name, setName] = useState('')
  const [subject, setSubject] = useState('金融学')
  const [desc, setDesc] = useState('')
  const [prompt, setPrompt] = useState('')
  const [saved, setSaved] = useState(false)

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim() || !desc.trim() || !prompt.trim()) return
    setSaved(true)
    setTimeout(() => navigate('/workspace/my-agents'), 1200)
  }

  // 步骤一：选择类型
  if (!agentType) {
    return (
      <div style={{ flex: 1, overflowY: 'auto', padding: '32px 36px', background: 'var(--bg)' }}>
        <div style={{ maxWidth: 680, margin: '0 auto' }}>
          <div style={{ marginBottom: 32 }}>
            <div style={{ fontSize: 10, fontFamily: "'JetBrains Mono', monospace", textTransform: 'uppercase' as const, letterSpacing: '0.3em', color: 'var(--text-muted)', marginBottom: 6 }}>// CREATE AGENT</div>
            <h1 style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>创建智能体</h1>
            <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>请先选择智能体类型</p>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
            {/* Prompt 智能体 */}
            <button
              onClick={() => setAgentType('prompt')}
              style={{ background: 'var(--surface)', border: '2px solid var(--border)', borderRadius: 12, padding: '28px 24px', textAlign: 'left' as const, cursor: 'pointer', fontFamily: 'inherit', transition: 'border-color 0.2s, box-shadow 0.2s' }}
              onMouseEnter={e => { (e.currentTarget as HTMLElement).style.borderColor = 'var(--action)'; (e.currentTarget as HTMLElement).style.boxShadow = '0 4px 16px rgba(23,73,196,0.08)' }}
              onMouseLeave={e => { (e.currentTarget as HTMLElement).style.borderColor = 'var(--border)'; (e.currentTarget as HTMLElement).style.boxShadow = 'none' }}
            >
              <div style={{ fontSize: 32, marginBottom: 14 }}>💬</div>
              <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 8 }}>Prompt 智能体</div>
              <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.65, marginBottom: 16 }}>
                通过编写系统提示词定义智能体的分析角色、步骤和输出格式。无需代码，填写即可使用。
              </div>
              <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>适合：分析流程固定、逻辑清晰的场景</div>
            </button>

            {/* 独立部署 Agent */}
            <button
              onClick={() => setAgentType('deployed')}
              style={{ background: 'var(--surface)', border: '2px solid var(--border)', borderRadius: 12, padding: '28px 24px', textAlign: 'left' as const, cursor: 'pointer', fontFamily: 'inherit', transition: 'border-color 0.2s, box-shadow 0.2s' }}
              onMouseEnter={e => { (e.currentTarget as HTMLElement).style.borderColor = '#7C3AED'; (e.currentTarget as HTMLElement).style.boxShadow = '0 4px 16px rgba(124,58,237,0.08)' }}
              onMouseLeave={e => { (e.currentTarget as HTMLElement).style.borderColor = 'var(--border)'; (e.currentTarget as HTMLElement).style.boxShadow = 'none' }}
            >
              <div style={{ fontSize: 32, marginBottom: 14 }}>🚀</div>
              <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 8 }}>独立部署 Agent</div>
              <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.65, marginBottom: 16 }}>
                需要自定义工具、外部 API 接入或复杂工作流的 Agent，由平台后台团队协助部署。
              </div>
              <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>适合：需要调用特定数据源或工具的复杂场景</div>
            </button>
          </div>
        </div>
      </div>
    )
  }

  // 独立部署：联系信息页
  if (agentType === 'deployed') {
    return (
      <div style={{ flex: 1, overflowY: 'auto', padding: '32px 36px', background: 'var(--bg)' }}>
        <div style={{ maxWidth: 560, margin: '0 auto' }}>
          <button onClick={() => setAgentType(null)} style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontFamily: 'inherit', fontSize: 13, marginBottom: 24, padding: 0 }}>
            ← 重新选择类型
          </button>
          <div style={{ marginBottom: 28 }}>
            <div style={{ fontSize: 10, fontFamily: "'JetBrains Mono', monospace", textTransform: 'uppercase' as const, letterSpacing: '0.3em', color: 'var(--text-muted)', marginBottom: 6 }}>// DEPLOY AGENT</div>
            <h1 style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>独立部署 Agent</h1>
            <p style={{ fontSize: 13, color: 'var(--text-muted)', lineHeight: 1.7 }}>
              独立部署 Agent 需要后台团队协助配置环境、工具和 API 接入。请联系以下负责人说明你的需求。
            </p>
          </div>

          <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12, overflow: 'hidden', marginBottom: 20 }}>
            <div style={{ padding: '14px 20px', background: 'var(--bg)', borderBottom: '1px solid var(--border)', fontSize: 11, fontFamily: "'JetBrains Mono', monospace", textTransform: 'uppercase' as const, letterSpacing: '0.2em', color: 'var(--text-muted)' }}>
              // CONTACT
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

          <div style={{ background: '#FFFBEB', border: '1px solid #FDE68A', borderRadius: 8, padding: '12px 16px', fontSize: 13, color: '#92400E', lineHeight: 1.7 }}>
            💡 联系时请说明：智能体的功能描述、需要接入的外部数据源或工具、预期的输入输出格式。
          </div>
        </div>
      </div>
    )
  }

  // Prompt 智能体创建表单
  if (saved) {
    return (
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--bg)' }}>
        <div style={{ textAlign: 'center' as const }}>
          <div style={{ fontSize: 40, marginBottom: 16 }}>✓</div>
          <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 8 }}>已创建</div>
          <div style={{ fontSize: 14, color: 'var(--text-muted)' }}>智能体已保存，跳转至「我的智能体」...</div>
        </div>
      </div>
    )
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '32px 36px', background: 'var(--bg)' }}>
      <div style={{ maxWidth: 720, margin: '0 auto' }}>
        <button onClick={() => setAgentType(null)} style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontFamily: 'inherit', fontSize: 13, marginBottom: 24, padding: 0 }}>
          ← 重新选择类型
        </button>
        <div style={{ marginBottom: 28 }}>
          <div style={{ fontSize: 10, fontFamily: "'JetBrains Mono', monospace", textTransform: 'uppercase' as const, letterSpacing: '0.3em', color: 'var(--text-muted)', marginBottom: 6 }}>// CREATE PROMPT AGENT</div>
          <h1 style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>创建 Prompt 智能体</h1>
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
              <textarea value={desc} onChange={e => setDesc(e.target.value)} placeholder="简要描述分析场景与产出结果" style={{ ...inputStyle, minHeight: 80, resize: 'vertical' as const }} maxLength={200} />
            </FormField>
          </div>

          {/* 方法论配置 */}
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
            <button type="button" onClick={() => navigate('/workspace/my-agents')} style={{ padding: '9px 20px', background: 'var(--surface)', color: 'var(--text-secondary)', border: '1px solid var(--border)', borderRadius: 7, fontSize: 13, cursor: 'pointer', fontFamily: 'inherit' }}>取消</button>
            <button type="submit" style={{ padding: '9px 20px', background: 'var(--action)', color: '#fff', border: 'none', borderRadius: 7, fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>保存</button>
          </div>
        </form>
      </div>
    </div>
  )
}
