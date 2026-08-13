import { useState } from 'react'
import { PublishDialog } from '../components/PublishDialog'

type ScenarioStatus = 'created' | 'reviewing' | 'published'

interface MyScenario {
  id: string
  name: string
  description?: string
  subject: string
  prompt: string
  skills: string
  mcp: string
  status: ScenarioStatus
  calls?: number
  submittedAt?: string
  publishedAt?: string
}

const STATUS_LABEL: Record<ScenarioStatus, string> = {
  created: '已创建',
  reviewing: '待审核',
  published: '已发布',
}

const STATUS_STYLE: Record<ScenarioStatus, { bg: string; color: string }> = {
  created: { bg: '#EFF6FF', color: '#2563EB' },
  reviewing: { bg: '#FFFBEB', color: 'var(--status-warn)' },
  published: { bg: '#ECFDF5', color: 'var(--status-done)' },
}

const MOCK_SCENARIOS: MyScenario[] = [
  { id: '1', name: '企业风险分析', subject: '金融学', prompt: '识别企业经营和财务风险，输出证据链与风险建议。', skills: '财务指标计算、数据清洗、图表生成', mcp: '财报检索服务', status: 'published', calls: 84, publishedAt: '2026-07-25' },
  { id: '2', name: '实证论文稳健性复核', subject: '经济学', prompt: '按论文复现流程检查数据、模型设定和稳健性结论。', skills: '回归诊断、表格提取', mcp: '学术文献检索', status: 'reviewing', submittedAt: '2026-08-11 15:18' },
  { id: '3', name: '上市公司同业比较', subject: '会计学', prompt: '选择可比公司，对核心财务指标进行横向比较。', skills: '财务指标计算、图表生成', mcp: '', status: 'created' },
]

const TABS: ScenarioStatus[] = ['created', 'reviewing', 'published']
const EMPTY_FORM = { name: '', subject: '', prompt: '', skills: '', mcp: '' }

export function MyScenarios() {
  const [activeTab, setActiveTab] = useState<ScenarioStatus>('created')
  const [scenarios, setScenarios] = useState(MOCK_SCENARIOS)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [form, setForm] = useState(EMPTY_FORM)
  const [showEditor, setShowEditor] = useState(false)
  const [publishingId, setPublishingId] = useState<string | null>(null)

  const filtered = scenarios.filter(scenario => scenario.status === activeTab)
  const formReady = Boolean(form.name.trim() && form.subject.trim() && form.prompt.trim() && form.skills.trim())

  const openCreate = () => {
    setEditingId(null)
    setForm(EMPTY_FORM)
    setShowEditor(true)
  }

  const openEdit = (scenario: MyScenario) => {
    setEditingId(scenario.id)
    setForm({ name: scenario.name, subject: scenario.subject, prompt: scenario.prompt, skills: scenario.skills, mcp: scenario.mcp })
    setShowEditor(true)
  }

  const saveScenario = (event: React.FormEvent) => {
    event.preventDefault()
    if (!formReady) return
    if (editingId) {
      setScenarios(current => current.map(scenario => scenario.id === editingId ? { ...scenario, ...form } : scenario))
    } else {
      setScenarios(current => [{ id: String(Date.now()), ...form, status: 'created' }, ...current])
      setActiveTab('created')
    }
    setShowEditor(false)
  }

  const submitForReview = (id: string, name: string, description: string) => {
    setScenarios(current => current.map(scenario => scenario.id === id ? { ...scenario, name, description, status: 'reviewing', submittedAt: '刚刚' } : scenario))
    setPublishingId(null)
    setActiveTab('reviewing')
  }

  const takeOffline = (id: string) => {
    setScenarios(current => current.map(scenario => scenario.id === id ? { ...scenario, status: 'created', publishedAt: undefined } : scenario))
    setActiveTab('created')
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '32px 36px', background: 'var(--bg)' }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 24, marginBottom: 28 }}>
        <div>
          <div style={eyebrowStyle}>// MY SCENARIOS</div>
          <h1 style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>我的场景</h1>
          <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>管理由系统提示词、Skills 和 MCP 组合而成的分析场景</p>
        </div>
        <button type="button" onClick={openCreate} style={primaryButtonStyle}>+ 创建场景</button>
      </div>

      <div style={{ display: 'flex', borderBottom: '1px solid var(--border)', marginBottom: 20 }}>
        {TABS.map(tab => (
          <button type="button" key={tab} onClick={() => setActiveTab(tab)} style={{ ...tabStyle, borderBottomColor: activeTab === tab ? 'var(--action)' : 'transparent', color: activeTab === tab ? 'var(--action)' : 'var(--text-muted)' }}>
            {STATUS_LABEL[tab]}
            <span style={countStyle}>{scenarios.filter(scenario => scenario.status === tab).length}</span>
          </button>
        ))}
      </div>

      {filtered.length === 0 ? (
        <div style={emptyStyle}>
          <div style={{ fontSize: 14, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 12 }}>该状态下还没有场景</div>
          {activeTab === 'created' && <button type="button" onClick={openCreate} style={primaryButtonStyle}>+ 创建场景</button>}
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {filtered.map(scenario => (
            <div key={scenario.id} style={rowStyle}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 5, flexWrap: 'wrap' }}>
                  <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>{scenario.name}</span>
                  <span style={{ ...statusStyle, background: STATUS_STYLE[scenario.status].bg, color: STATUS_STYLE[scenario.status].color }}>{STATUS_LABEL[scenario.status]}</span>
                  {scenario.calls !== undefined && <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{scenario.calls} 次调用</span>}
                </div>
                <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 5 }}>{scenario.prompt}</div>
                <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 4 }}>{scenario.subject} · 系统提示词 · {scenario.skills.split('、').filter(Boolean).length} Skills · {scenario.mcp ? '1 MCP' : '无 MCP'}</div>
                <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                  Skills：{scenario.skills}
                  {scenario.publishedAt && ` · ${scenario.publishedAt} 发布`}
                  {scenario.submittedAt && ` · ${scenario.submittedAt} 提交审核`}
                </div>
              </div>
              <div style={{ display: 'flex', gap: 8, flexShrink: 0 }}>
                {scenario.status === 'created' && <><button type="button" onClick={() => openEdit(scenario)} style={secondaryButtonStyle}>编辑</button><button type="button" onClick={() => setPublishingId(scenario.id)} style={outlineActionStyle}>发布到场景库</button></>}
                {scenario.status === 'reviewing' && <span style={waitingStyle}>等待审核</span>}
                {scenario.status === 'published' && <><button type="button" onClick={() => openEdit(scenario)} style={secondaryButtonStyle}>编辑</button><button type="button" onClick={() => takeOffline(scenario.id)} style={dangerButtonStyle}>下线</button></>}
              </div>
            </div>
          ))}
        </div>
      )}

      {publishingId && (() => {
        const scenario = scenarios.find(item => item.id === publishingId)
        return scenario ? <PublishDialog kindLabel="场景" initialName={scenario.name} initialDescription={scenario.description ?? scenario.prompt} existingNames={[...scenarios.filter(item => item.status === 'published').map(item => item.name), '论文量化复现', '课题数据分析', '量化因子研究', '三表勾稽核查']} onClose={() => setPublishingId(null)} onSubmit={(name, description) => submitForReview(scenario.id, name, description)} /> : null
      })()}

      {showEditor && (
        <>
          <div onClick={() => setShowEditor(false)} style={backdropStyle} />
          <div style={modalStyle}>
            <div style={modalHeaderStyle}><div><div style={{ fontSize: 17, fontWeight: 700, color: 'var(--text-primary)' }}>{editingId ? '编辑场景' : '创建场景'}</div><div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>场景由系统提示词、Skills 与可选 MCP 工具组合。</div></div><button type="button" onClick={() => setShowEditor(false)} style={closeStyle}>×</button></div>
            <form onSubmit={saveScenario}>
              <FormField label="场景名称" value={form.name} onChange={name => setForm(current => ({ ...current, name }))} placeholder="请输入场景名称" />
              <FormField label="学科分类" value={form.subject} onChange={subject => setForm(current => ({ ...current, subject }))} placeholder="如：金融学 / 会计学" />
              <FormArea label="系统提示词" value={form.prompt} onChange={prompt => setForm(current => ({ ...current, prompt }))} placeholder="说明分析目标、流程约束与输出格式" />
              <FormField label="Skills" value={form.skills} onChange={skills => setForm(current => ({ ...current, skills }))} placeholder="多个 Skill 使用顿号分隔" />
              <FormField label="MCP（可选）" value={form.mcp} onChange={mcp => setForm(current => ({ ...current, mcp }))} placeholder="填写平台已放行的 MCP 工具" required={false} />
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}><button type="button" onClick={() => setShowEditor(false)} style={secondaryButtonStyle}>取消</button><button type="submit" disabled={!formReady} style={{ ...primaryButtonStyle, background: formReady ? 'var(--action)' : 'var(--text-muted)', cursor: formReady ? 'pointer' : 'default' }}>保存</button></div>
            </form>
          </div>
        </>
      )}
    </div>
  )
}

function FormField({ label, value, onChange, placeholder, required = true }: { label: string; value: string; onChange: (value: string) => void; placeholder: string; required?: boolean }) {
  return <div style={{ marginBottom: 16 }}><label style={labelStyle}>{label} {required && <span style={{ color: '#DC2626' }}>*</span>}</label><input value={value} onChange={event => onChange(event.target.value)} placeholder={placeholder} style={inputStyle} /></div>
}

function FormArea({ label, value, onChange, placeholder }: { label: string; value: string; onChange: (value: string) => void; placeholder: string }) {
  return <div style={{ marginBottom: 16 }}><label style={labelStyle}>{label} <span style={{ color: '#DC2626' }}>*</span></label><textarea value={value} onChange={event => onChange(event.target.value)} placeholder={placeholder} style={{ ...inputStyle, minHeight: 90, resize: 'vertical' }} /></div>
}

const eyebrowStyle: React.CSSProperties = { fontSize: 10, fontFamily: "'JetBrains Mono', monospace", textTransform: 'uppercase', letterSpacing: '0.3em', color: 'var(--text-muted)', marginBottom: 6 }
const primaryButtonStyle: React.CSSProperties = { padding: '9px 20px', background: 'var(--action)', color: '#fff', border: 'none', borderRadius: 7, fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit', flexShrink: 0 }
const tabStyle: React.CSSProperties = { padding: '10px 20px', fontSize: 13, fontWeight: 500, background: 'none', border: 'none', borderBottom: '2px solid transparent', marginBottom: -1, cursor: 'pointer', fontFamily: 'inherit' }
const countStyle: React.CSSProperties = { marginLeft: 6, fontSize: 11, background: 'var(--bg)', padding: '1px 6px', borderRadius: 10, color: 'var(--text-muted)' }
const emptyStyle: React.CSSProperties = { background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, padding: '48px 20px', textAlign: 'center' }
const rowStyle: React.CSSProperties = { background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, padding: '16px 20px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16 }
const statusStyle: React.CSSProperties = { padding: '1px 7px', borderRadius: 10, fontSize: 11, fontWeight: 600 }
const secondaryButtonStyle: React.CSSProperties = { padding: '7px 14px', background: 'transparent', color: 'var(--text-secondary)', border: '1px solid var(--border)', borderRadius: 6, fontSize: 12, cursor: 'pointer', fontFamily: 'inherit' }
const outlineActionStyle: React.CSSProperties = { ...secondaryButtonStyle, color: 'var(--action)', borderColor: 'var(--action-border)' }
const dangerButtonStyle: React.CSSProperties = { ...secondaryButtonStyle, color: '#DC2626', borderColor: '#FECACA' }
const waitingStyle: React.CSSProperties = { fontSize: 12, color: 'var(--text-muted)', padding: '7px 0' }
const backdropStyle: React.CSSProperties = { position: 'fixed', inset: 0, background: 'rgba(13,24,41,0.4)', backdropFilter: 'blur(4px)', zIndex: 300 }
const modalStyle: React.CSSProperties = { position: 'fixed', top: '50%', left: '50%', transform: 'translate(-50%,-50%)', width: 520, maxHeight: 'calc(100vh - 64px)', overflowY: 'auto', padding: 30, background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12, boxShadow: '0 20px 60px rgba(11,46,92,0.2)', zIndex: 301 }
const modalHeaderStyle: React.CSSProperties = { display: 'flex', justifyContent: 'space-between', gap: 16, alignItems: 'flex-start', marginBottom: 22 }
const closeStyle: React.CSSProperties = { border: 'none', background: 'none', color: 'var(--text-muted)', fontSize: 20, cursor: 'pointer' }
const labelStyle: React.CSSProperties = { display: 'block', fontSize: 13, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 6 }
const inputStyle: React.CSSProperties = { width: '100%', boxSizing: 'border-box', padding: '9px 12px', border: '1px solid var(--border)', borderRadius: 7, background: 'var(--surface)', color: 'var(--text-primary)', fontSize: 13, fontFamily: 'inherit', outline: 'none' }
