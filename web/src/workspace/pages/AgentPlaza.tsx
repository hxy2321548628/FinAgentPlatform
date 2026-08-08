import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

interface Agent {
  id: string; name: string; author: string; subject: string
  desc: string; dataNeeded: string; calls: number; rating: number; version: string
}

const SUBJECTS_FILTER = ['全部', '金融', '会计', '经济', '管理']
const SUBJECT_OPTIONS = ['金融学', '会计学', '经济学', '管理科学', '其他']

const MOCK_AGENTS: Agent[] = [
  { id: '1', name: '企业财务异常检测', author: '张老师', subject: '金融', desc: '对报表关键科目进行稽核式比率检查，识别异常项并输出清单。', dataNeeded: '财报 Excel / CSV', calls: 96, rating: 4.8, version: 'v1.2' },
  { id: '2', name: '计量方法识别', author: '赵老师', subject: '经济', desc: '识别论文使用的识别策略与计量方法（DID/RDD/IV），提取模型设定与稳健性检验清单。', dataNeeded: '论文 PDF', calls: 64, rating: 4.7, version: 'v1.1' },
  { id: '3', name: '公告语义分析', author: '平台 · 公共', subject: '金融', desc: '对上市公司公告进行语义分析，识别经营/治理/前瞻三类风险信号。', dataNeeded: '公告文本 / PDF', calls: 88, rating: 4.6, version: 'v1.0' },
  { id: '4', name: '申请书结构解析', author: '孙老师', subject: '管理', desc: '解析国家自然科学基金申请书的章节结构、立项依据与研究方案组织方式。', dataNeeded: '申请书 PDF', calls: 38, rating: 4.5, version: 'v1.0' },
  { id: '5', name: '创新点分析', author: '张老师', subject: '金融', desc: '对比目标文本与领域近期文献，分析创新点的表述方式与支撑证据是否充分。', dataNeeded: '论文 PDF', calls: 29, rating: 4.4, version: 'v1.0' },
  { id: '6', name: '财务报表核查', author: '陈老师', subject: '会计', desc: '按表关键科目衔接与勾稽关系做动态检查，输出异常项清单。', dataNeeded: '财报 CSV / Excel', calls: 61, rating: 4.6, version: 'v1.0' },
]

function AgentCard({ agent, onUse }: { agent: Agent; onUse: () => void }) {
  const [hovered, setHovered] = useState(false)
  return (
    <div onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)} style={{ background: 'var(--surface)', border: '1px solid ' + (hovered ? 'var(--action-border)' : 'var(--border)'), borderRadius: 10, padding: 24, display: 'flex', flexDirection: 'column' as const, gap: 10, boxShadow: hovered ? '0 4px 16px rgba(23,73,196,0.08)' : 'none', transition: 'border-color 0.2s, box-shadow 0.2s' }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
        <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)' }}>📊 {agent.name}</div>
        <span style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: "'JetBrains Mono', monospace", flexShrink: 0, marginLeft: 8 }}>{agent.version}</span>
      </div>
      <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{agent.author} · {agent.subject}</div>
      <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.65, flex: 1 }}>{agent.desc}</p>
      <div style={{ fontSize: 12, color: 'var(--text-muted)', padding: '8px 0', borderTop: '1px solid var(--border-light)', borderBottom: '1px solid var(--border-light)' }}>需要：{agent.dataNeeded}</div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: 12, color: 'var(--text-muted)' }}>
        <span>▶ {agent.calls} 次调用</span>
        <span>⭐ {agent.rating}</span>
      </div>
      <button onClick={onUse} style={{ width: '100%', padding: '8px 0', background: 'var(--action)', color: '#fff', border: 'none', borderRadius: 7, fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>使用此 Agent</button>
    </div>
  )
}

export function AgentPlaza() {
  const navigate = useNavigate()
  const [activeSubject, setActiveSubject] = useState('全部')
  const [sortBy, setSortBy] = useState<'calls' | 'rating'>('calls')
  const filtered = MOCK_AGENTS.filter(a => activeSubject === '全部' || a.subject === activeSubject).sort((a, b) => b[sortBy] - a[sortBy])
  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '32px 36px', background: 'var(--bg)' }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 28 }}>
        <div>
          <div style={{ fontSize: 10, fontFamily: "'JetBrains Mono', monospace", textTransform: 'uppercase' as const, letterSpacing: '0.3em', color: 'var(--text-muted)', marginBottom: 6 }}>// AGENT PLAZA</div>
          <h1 style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>智能体广场</h1>
          <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>浏览并使用其他老师发布的分析智能体</p>
        </div>
        <button onClick={() => navigate('/workspace/agents/new')} style={{ padding: '9px 20px', background: 'var(--action)', color: '#fff', border: 'none', borderRadius: 7, fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit', flexShrink: 0 }}>+ 发布我的智能体</button>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20, flexWrap: 'wrap' as const, gap: 10 }}>
        <div style={{ display: 'flex', gap: 8 }}>
          {SUBJECTS_FILTER.map(s => (
            <button key={s} onClick={() => setActiveSubject(s)} style={{ padding: '5px 14px', borderRadius: 20, border: '1px solid ' + (activeSubject === s ? 'var(--action)' : 'var(--border)'), background: activeSubject === s ? 'var(--action)' : 'var(--surface)', color: activeSubject === s ? '#fff' : 'var(--text-secondary)', fontSize: 12, fontWeight: activeSubject === s ? 600 : 400, cursor: 'pointer', fontFamily: 'inherit', transition: 'all 0.15s' }}>{s}</button>
          ))}
        </div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>排序：</span>
          {(['calls', 'rating'] as const).map(s => (
            <button key={s} onClick={() => setSortBy(s)} style={{ padding: '5px 12px', borderRadius: 6, border: '1px solid ' + (sortBy === s ? 'var(--action-border)' : 'var(--border)'), background: sortBy === s ? 'var(--action-light)' : 'var(--surface)', color: sortBy === s ? 'var(--action)' : 'var(--text-secondary)', fontSize: 12, cursor: 'pointer', fontFamily: 'inherit' }}>
              {s === 'calls' ? '调用次数' : '评分'}
            </button>
          ))}
        </div>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
        {filtered.map(agent => <AgentCard key={agent.id} agent={agent} onUse={() => navigate('/workspace/chat')} />)}
      </div>
    </div>
  )
}

function FormField({ label, required, hint, children }: { label: string; required?: boolean; hint?: string; children: React.ReactNode }) {
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

const inputStyle: React.CSSProperties = { width: '100%', padding: '9px 12px', border: '1px solid var(--border)', borderRadius: 7, fontSize: 13, color: 'var(--text-primary)', background: '#F7F9FC', outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' as const }

export function PublishAgent() {
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [subject, setSubject] = useState('金融学')
  const [desc, setDesc] = useState('')
  const [dataNeeded, setDataNeeded] = useState('')
  const [prompt, setPrompt] = useState('')
  const [submitted, setSubmitted] = useState(false)

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim() || !desc.trim() || !prompt.trim()) return
    setSubmitted(true)
    setTimeout(() => navigate('/workspace/my-agents'), 1500)
  }

  if (submitted) {
    return (
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--bg)' }}>
        <div style={{ textAlign: 'center' as const }}>
          <div style={{ fontSize: 40, marginBottom: 16 }}>✓</div>
          <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 8 }}>已提交审核</div>
          <div style={{ fontSize: 14, color: 'var(--text-muted)' }}>跳转至「我的智能体」...</div>
        </div>
      </div>
    )
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '32px 36px', background: 'var(--bg)' }}>
      <div style={{ maxWidth: 720, margin: '0 auto' }}>
        <div style={{ marginBottom: 28 }}>
          <div style={{ fontSize: 10, fontFamily: "'JetBrains Mono', monospace", textTransform: 'uppercase' as const, letterSpacing: '0.3em', color: 'var(--text-muted)', marginBottom: 6 }}>// PUBLISH AGENT</div>
          <h1 style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>发布智能体</h1>
          <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>将你的分析方法封装成可复用的智能体，提交审核后发布到广场</p>
        </div>
        <form onSubmit={handleSubmit}>
          <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, padding: 24, marginBottom: 16 }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 20 }}>基本信息</div>
            <FormField label="智能体名称" required><input value={name} onChange={e => setName(e.target.value)} placeholder="如：企业财务异常检测" style={inputStyle} /></FormField>
            <FormField label="所属学科">
              <select value={subject} onChange={e => setSubject(e.target.value)} style={{ ...inputStyle, cursor: 'pointer' }}>
                {SUBJECT_OPTIONS.map(s => <option key={s}>{s}</option>)}
              </select>
            </FormField>
            <FormField label="功能描述" required hint="广场展示用，200 字以内"><textarea value={desc} onChange={e => setDesc(e.target.value)} placeholder="简要描述这个智能体能做什么、适用于什么场景" style={{ ...inputStyle, minHeight: 80, resize: 'vertical' as const }} maxLength={200} /></FormField>
            <FormField label="所需数据" hint="告知使用者需要上传什么格式的文件"><input value={dataNeeded} onChange={e => setDataNeeded(e.target.value)} placeholder="如：财报 CSV / Excel，上市公司 A 股数据" style={inputStyle} /></FormField>
          </div>
          <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, padding: 24, marginBottom: 24 }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 4 }}>方法论配置</div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 16 }}>这段文字将作为 AI 的「工作说明」，决定智能体的分析角度和输出格式</div>
            <FormField label="系统提示词" required><textarea value={prompt} onChange={e => setPrompt(e.target.value)} placeholder={'你是一位专业的财务分析师...\n\n请按以下步骤完成分析：\n1. 读取数据，了解结构\n2. 计算关键财务指标...'} style={{ ...inputStyle, minHeight: 200, resize: 'vertical' as const, fontFamily: "'JetBrains Mono', monospace", fontSize: 12, lineHeight: 1.7 }} /></FormField>
          </div>
          <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
            <button type="button" onClick={() => navigate('/workspace/agents')} style={{ padding: '9px 20px', background: 'var(--surface)', color: 'var(--text-secondary)', border: '1px solid var(--border)', borderRadius: 7, fontSize: 13, cursor: 'pointer', fontFamily: 'inherit' }}>取消</button>
            <button type="submit" style={{ padding: '9px 20px', background: 'var(--action)', color: '#fff', border: 'none', borderRadius: 7, fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>提交审核</button>
          </div>
        </form>
      </div>
    </div>
  )
}
