import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

interface Scenario {
  id: string
  name: string
  subject: string
  subjectTag: string
  desc: string
  tags: string[]
  steps: number
  author: string
  uses: number
  agentName?: string   // 关联的 agent 名称
  agentAuthor?: string // agent 创建者，platform 表示平台内置
}

const SUBJECTS = ['全部', '金融学', '会计学', '经济学', '管理科学']

const MOCK_SCENARIOS: Scenario[] = [
  { id: 'risk', name: '企业风险分析', subject: '金融学', subjectTag: '金融学 · 产业研究', desc: '上传财报 CSV，识别偿债/盈利/运营风险信号，输出带证据链的风险报告草稿。', tags: ['财务分析', '风险识别', '报告生成'], steps: 5, author: '金融学院', uses: 127, agentName: '企业财务异常检测', agentAuthor: '张老师' },
  { id: 'replicate', name: '论文量化复现', subject: '金融学', subjectTag: '金融学 / 经济学 · 学术研究', desc: '上传数据集，复现回归模型，验证论文中的 alpha 显著性，输出复现报告。', tags: ['计量方法', '回归分析', '复现验证'], steps: 4, author: '金融学院', uses: 89, agentName: '计量方法识别', agentAuthor: '赵老师' },
  { id: 'survey', name: '课题数据分析', subject: '管理科学', subjectTag: '全学科 · 科研支持', desc: '上传问卷或面板数据，进行描述统计、假设检验与可视化，输出分析结论。', tags: ['描述统计', '假设检验', '可视化'], steps: 4, author: '金融学院', uses: 203 },
  { id: 'factor', name: '量化因子研究', subject: '金融学', subjectTag: '金融学 · 量化投资', desc: '上传股票行情数据，构建因子序列，检验 alpha 显著性，生成因子收益图表。', tags: ['因子模型', 'Fama-French', 'alpha 检验'], steps: 5, author: '金融学院', uses: 64 },
]

function ScenarioCard({ scenario, onStart }: { scenario: Scenario; onStart: () => void }) {
  const [hovered, setHovered] = useState(false)
  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{ background: 'var(--surface)', border: '1px solid ' + (hovered ? 'var(--action-border)' : 'var(--border)'), borderRadius: 10, padding: 24, display: 'flex', flexDirection: 'column' as const, gap: 12, boxShadow: hovered ? '0 4px 16px rgba(23,73,196,0.08)' : 'none', transition: 'border-color 0.2s, box-shadow 0.2s' }}
    >
      <div>
        <div style={{ fontSize: 17, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>{scenario.name}</div>
        <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{scenario.subjectTag}</div>
      </div>
      <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.7, flex: 1 }}>{scenario.desc}</p>
      <div style={{ display: 'flex', flexWrap: 'wrap' as const, gap: 6 }}>
        {scenario.tags.map(tag => (
          <span key={tag} style={{ padding: '2px 8px', fontSize: 11, fontWeight: 500, color: 'var(--text-secondary)', border: '1px solid var(--border)', borderRadius: 3 }}>{tag}</span>
        ))}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingTop: 10, borderTop: '1px solid var(--border-light)', fontSize: 12, color: 'var(--text-muted)' }}>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
          {scenario.steps} 步分析
          <span style={{ margin: '0 4px', color: 'var(--border)' }}>·</span>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
          {scenario.author}
        </span>
        <span>▶ {scenario.uses} 次</span>
      </div>
      {scenario.agentName && (
        <div style={{ fontSize: 11, color: 'var(--text-muted)', paddingTop: 6 }}>
          基于智能体：<span style={{ color: 'var(--action)', fontWeight: 500 }}>{scenario.agentName}</span>
          {scenario.agentAuthor && <span> · {scenario.agentAuthor}</span>}
        </div>
      )}
      <button onClick={onStart} style={{ width: '100%', padding: '9px 0', background: 'var(--action)', color: '#fff', border: 'none', borderRadius: 7, fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit', transition: 'background 0.15s' }}>开始分析 →</button>
    </div>
  )
}

export function AgentScenarios() {
  const navigate = useNavigate()
  const [activeSubject, setActiveSubject] = useState('全部')
  const filtered = activeSubject === '全部' ? MOCK_SCENARIOS : MOCK_SCENARIOS.filter(s => s.subject === activeSubject)
  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '32px 36px', background: 'var(--bg)' }}>
      <div style={{ marginBottom: 28 }}>
        <div style={{ fontSize: 10, fontFamily: "'JetBrains Mono', monospace", textTransform: 'uppercase' as const, letterSpacing: '0.3em', color: 'var(--text-muted)', marginBottom: 6 }}>// SCENARIOS</div>
        <h1 style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>场景库</h1>
        <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>选择分析场景，一键启动预配置的智能体分析流程</p>
      </div>
      <div style={{ display: 'flex', gap: 8, marginBottom: 24, flexWrap: 'wrap' as const }}>
        {SUBJECTS.map(s => (
          <button key={s} onClick={() => setActiveSubject(s)} style={{ padding: '6px 16px', borderRadius: 20, border: '1px solid ' + (activeSubject === s ? 'var(--action)' : 'var(--border)'), background: activeSubject === s ? 'var(--action)' : 'var(--surface)', color: activeSubject === s ? '#fff' : 'var(--text-secondary)', fontSize: 13, fontWeight: activeSubject === s ? 600 : 400, cursor: 'pointer', fontFamily: 'inherit', transition: 'all 0.15s' }}>{s}</button>
        ))}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
        {filtered.map(scenario => <ScenarioCard key={scenario.id} scenario={scenario} onStart={() => navigate('/workspace/chat', {
          state: scenario.agentName ? {
            agentId: scenario.id,
            agentName: scenario.agentName,
            agentAuthor: scenario.agentAuthor ?? scenario.author,
            agentDataNeeded: '',
          } : null
        })} />)}
      </div>
    </div>
  )
}
