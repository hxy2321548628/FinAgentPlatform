import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { CatalogCard, CatalogControls } from '../components/Catalog'

interface Scenario {
  id: string
  name: string
  subject: string
  subjectTag: string
  desc: string
  author: string
  uses: number
  version: string
  prompt: string
  skills: string[]
  mcp: string[]
}

const SUBJECTS = ['全部', '金融学', '会计学', '经济学', '管理科学'].map(key => ({ key, label: key }))

const MOCK_SCENARIOS: Scenario[] = [
  { id: 'risk', name: '企业风险分析', subject: '金融学', subjectTag: '金融学 · 产业研究', desc: '上传财报 CSV，识别偿债、盈利与运营风险信号，输出带证据链的风险报告草稿。', author: '金融学院', uses: 127, version: 'v1.2', prompt: '以企业风险分析师身份检查财务指标、异常变化与行业差异，并生成可追溯的风险结论。', skills: ['财务指标计算', '异常检测', '报告生成'], mcp: ['财报检索服务'] },
  { id: 'replicate', name: '论文量化复现', subject: '经济学', subjectTag: '金融学 / 经济学 · 学术研究', desc: '上传论文和数据集，复现回归模型，验证论文中的 alpha 显著性并输出复现报告。', author: '金融学院', uses: 89, version: 'v1.1', prompt: '按照论文方法设定模型，记录数据处理、回归结果和偏差来源，形成可复核的复现过程。', skills: ['计量方法识别', '回归诊断', '复现报告'], mcp: ['学术文献检索'] },
  { id: 'survey', name: '课题数据分析', subject: '管理科学', subjectTag: '全学科 · 科研支持', desc: '上传问卷或面板数据，进行描述统计、假设检验与可视化，输出分析结论。', author: '金融学院', uses: 203, version: 'v1.3', prompt: '先检查数据质量与变量定义，再选择合适的统计方法并解释结果，不夸大因果关系。', skills: ['数据清洗', '假设检验', '图表生成'], mcp: [] },
  { id: 'factor', name: '量化因子研究', subject: '金融学', subjectTag: '金融学 · 量化投资', desc: '上传股票行情数据，构建因子序列，检验 alpha 显著性，生成因子收益图表。', author: '金融学院', uses: 64, version: 'v1.0', prompt: '以量化研究员身份构建并检验因子，完整报告样本区间、交易成本与稳健性结果。', skills: ['因子模型', '回测验证', '图表生成'], mcp: ['学院行情数据服务'] },
  { id: 'audit', name: '三表勾稽核查', subject: '会计学', subjectTag: '会计学 · 财务审计', desc: '核对资产负债表、利润表与现金流量表的勾稽关系，定位不一致项并给出核查建议。', author: '会计系', uses: 58, version: 'v1.0', prompt: '按会计恒等式和报表勾稽关系逐项核验，所有异常结论必须附带原始科目与数值证据。', skills: ['表格解析', '勾稽校验'], mcp: [] },
]

export function AgentScenarios() {
  const navigate = useNavigate()
  const [activeSubject, setActiveSubject] = useState('全部')
  const [search, setSearch] = useState('')
  const [detailScenario, setDetailScenario] = useState<Scenario | null>(null)

  const filtered = MOCK_SCENARIOS
    .filter(scenario => {
      const matchSubject = activeSubject === '全部' || scenario.subject === activeSubject
      const matchSearch = !search || scenario.name.includes(search) || scenario.desc.includes(search) || scenario.author.includes(search)
      return matchSubject && matchSearch
    })
    .sort((a, b) => b.uses - a.uses)

  const handleStart = (scenario: Scenario) => {
    navigate('/workspace/chat', {
      state: {
        agentId: scenario.id,
        agentName: scenario.name,
        agentAuthor: scenario.author,
        agentDataNeeded: '',
      }
    })
  }


  return (
    <div style={{ flex: 1, overflowY: 'auto', background: 'var(--bg)' }}>
      <div style={{ padding: '28px 36px 0' }}>
        <div style={{ fontSize: 10, fontFamily: "'JetBrains Mono', monospace", textTransform: 'uppercase', letterSpacing: '0.3em', color: 'var(--text-muted)', marginBottom: 6 }}>// SCENARIOS</div>
        <h1 style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>场景库</h1>
        <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>浏览由系统提示词、Skills 与 MCP 组合而成的分析流程，共 {MOCK_SCENARIOS.length} 个</p>
      </div>

      <CatalogControls
        search={search}
        onSearch={setSearch}
        placeholder="搜索场景名称、描述或发布者..."
        filters={SUBJECTS}
        activeFilter={activeSubject}
        onFilter={setActiveSubject}
      />

      <div style={{ padding: '0 36px' }}>
        {filtered.length === 0 ? (
          <div style={{ padding: '60px 0', textAlign: 'center', color: 'var(--text-muted)', fontSize: 14 }}>
            {search ? `未找到与「${search}」相关的场景` : '该分类暂时没有场景'}
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 16 }}>
            {filtered.map(scenario => (
              <CatalogCard
                key={scenario.id}
                title={scenario.name}
                version={scenario.version}
                author={scenario.author}
                subject={scenario.subjectTag}
                description={scenario.desc}
                detail={`组合：系统提示词 · ${scenario.skills.length} Skills · ${scenario.mcp.length} MCP`}
                badges={['系统提示词', ...scenario.skills.map(skill => `Skill · ${skill}`), ...scenario.mcp.map(server => `MCP · ${server}`)]}
                metric={`${scenario.uses} 次调用`}
                secondaryAction={{ label: '查看详情', onClick: () => setDetailScenario(scenario) }}
                primaryAction={{ label: '开始分析', onClick: () => handleStart(scenario) }}
              />
            ))}
          </div>
        )}
        <div style={{ padding: '20px 0 32px', textAlign: 'center' }}>
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>共 {filtered.length} 个场景</span>
        </div>
      </div>

      {detailScenario && (
        <>
          <div onClick={() => setDetailScenario(null)} style={{ position: 'fixed', inset: 0, background: 'rgba(13,24,41,0.3)', zIndex: 200 }} />
          <div style={{ position: 'fixed', top: 0, right: 0, bottom: 0, width: 460, background: 'var(--surface)', borderLeft: '1px solid var(--border)', zIndex: 201, display: 'flex', flexDirection: 'column', boxShadow: '-8px 0 24px rgba(11,46,92,0.12)' }}>
            <div style={{ padding: '20px 24px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div>
                <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)' }}>{detailScenario.name}</div>
                <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 3 }}>{detailScenario.author} · {detailScenario.subjectTag} · {detailScenario.version}</div>
              </div>
              <button type="button" onClick={() => setDetailScenario(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', fontSize: 20, lineHeight: 1 }}>×</button>
            </div>
            <div style={{ flex: 1, overflowY: 'auto', padding: '20px 24px' }}>
              <ScenarioDetail title="功能描述"><div style={detailTextStyle}>{detailScenario.desc}</div></ScenarioDetail>
              <ScenarioDetail title="系统提示词摘要"><div style={detailCodeStyle}>{detailScenario.prompt}</div></ScenarioDetail>
              <ScenarioDetail title={`Skills · ${detailScenario.skills.length}`}>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>{detailScenario.skills.map(skill => <span key={skill} style={detailBadgeStyle}>{skill}</span>)}</div>
              </ScenarioDetail>
              <ScenarioDetail title={`MCP · ${detailScenario.mcp.length}`}>
                {detailScenario.mcp.length > 0 ? <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>{detailScenario.mcp.map(server => <span key={server} style={detailBadgeStyle}>{server}</span>)}</div> : <div style={detailTextStyle}>该场景不依赖 MCP 服务</div>}
              </ScenarioDetail>
            </div>
            <div style={{ padding: '16px 24px', borderTop: '1px solid var(--border)' }}>
              <button type="button" onClick={() => { setDetailScenario(null); handleStart(detailScenario) }} style={{ width: '100%', padding: '11px 0', background: 'var(--action)', color: '#fff', border: 'none', borderRadius: 8, fontSize: 14, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>使用此场景开始分析 →</button>
            </div>
          </div>
        </>
      )}


    </div>
  )
}

function ScenarioDetail({ title, children }: { title: string; children: React.ReactNode }) {
  return <div style={{ marginBottom: 20 }}><div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 8 }}>{title}</div>{children}</div>
}

const detailTextStyle: React.CSSProperties = { fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.75 }
const detailCodeStyle: React.CSSProperties = { ...detailTextStyle, background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 6, padding: '12px 14px', fontFamily: "'JetBrains Mono', monospace" }
const detailBadgeStyle: React.CSSProperties = { padding: '4px 9px', fontSize: 12, color: 'var(--text-secondary)', border: '1px solid var(--border)', borderRadius: 4, background: 'var(--bg)' }
