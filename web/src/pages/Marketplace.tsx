import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { CatalogCard } from '../workspace/components/Catalog'

// ── 数据定义 ──────────────────────────────────────────────────
interface SceneAgent { name: string; author: string }

interface FeaturedScene {
  id: string
  name: string
  subject: string
  tagline: string          // 一句话叙事
  desc: string
  flow: string[]           // 分析流程步骤
  agents: SceneAgent[]     // 组成的 Agent
  tags: string[]
  uses: number
  duration: string         // 典型用时
}

interface AgentCard {
  id: string
  name: string
  author: string
  subject: string
  desc: string
  calls: number
  scenes: string[]         // 被哪些场景使用
}

const FEATURED_SCENES: FeaturedScene[] = [
  {
    id: 'risk',
    name: '企业财务风险分析',
    subject: '金融学',
    tagline: '上传财报，10 分钟得到带证据链的风险报告草稿',
    desc: '教师提供一份上市公司财报，平台自动核查三表勾稽、识别异常科目、对比行业基准，最终生成可直接用于教学或研究的风险分析报告。',
    flow: ['上传财报 CSV / Excel', '智能体核查三表勾稽关系', '识别偿债、盈利、运营三类风险信号', '对比行业基准数据', '生成带证据引用的分析报告'],
    agents: [
      { name: '企业财务异常检测', author: '张老师' },
      { name: '财务报表核查', author: '陈老师' },
    ],
    tags: ['财务分析', '风险识别', '报告生成'],
    uses: 127,
    duration: '约 8 分钟',
  },
  {
    id: 'paper',
    name: '论文计量方法鉴别',
    subject: '经济学',
    tagline: '上传论文，识别计量策略缺陷，生成审稿意见底稿',
    desc: '面向教师科研与课题组指导：上传一篇实证论文，系统自动识别识别策略类型、提取稳健性检验方法、标注潜在识别威胁，输出结构化审阅意见。',
    flow: ['上传论文 PDF', '识别核心识别策略（DID/RDD/IV）', '提取模型设定与控制变量逻辑', '检查稳健性检验完整性', '输出审阅意见与改进建议'],
    agents: [
      { name: '计量方法鉴别器', author: '赵老师' },
      { name: '创新点分析', author: '张老师' },
    ],
    tags: ['计量经济学', '论文审阅', '识别策略'],
    uses: 89,
    duration: '约 12 分钟',
  },
  {
    id: 'grant',
    name: '课题申请书诊断',
    subject: '管理科学',
    tagline: '对照已立项项目，找出申请书的结构差距',
    desc: '课题申请季必备工具：上传申请书草稿，系统自动对标同领域已立项项目的立项依据结构、创新点表述方式，输出差距清单和具体修改建议。',
    flow: ['上传申请书 PDF', '解析立项依据论证逻辑', '对比同领域已立项项目结构', '分析创新点表述与支撑证据', '输出差距清单和修改建议'],
    agents: [
      { name: '课题申请书诊断', author: '陈老师' },
      { name: '创新点分析', author: '张老师' },
    ],
    tags: ['申请书', '课题研究', '创新点分析'],
    uses: 64,
    duration: '约 15 分钟',
  },
  {
    id: 'factor',
    name: '量化因子研究',
    subject: '金融学',
    tagline: '上传股价数据，自动构建因子并检验 alpha 显著性',
    desc: '适合量化投资研究与教学：上传 A 股历史行情数据，系统自动计算动量、市值、盈利等因子，使用 Fama-French 框架回归并检验因子显著性，生成因子收益分析图表。',
    flow: ['上传股票日 K 数据', '计算动量、市值、盈利等因子', 'Fama-French 多因子回归', '检验 alpha 显著性（t 检验）', '生成因子收益对比图表'],
    agents: [
      { name: '量化因子筛选器', author: '李教授' },
    ],
    tags: ['量化投资', '因子模型', 'Fama-French'],
    uses: 52,
    duration: '约 6 分钟',
  },
]

const ALL_AGENTS: AgentCard[] = [
  { id: '1', name: '企业财务异常检测', author: '张老师', subject: '公司金融', desc: '对报表关键科目进行稽核式比率检查，识别异常项并输出带证据的清单。', calls: 96, scenes: ['企业财务风险分析'] },
  { id: '2', name: '计量方法鉴别器', author: '赵老师', subject: '学术科研', desc: '识别论文的识别策略类型，提取稳健性检验方法，标注识别威胁。', calls: 64, scenes: ['论文计量方法鉴别'] },
  { id: '3', name: '公告语义分析', author: '平台 · 公共', subject: '风险管理', desc: '解读上市公司公告，识别经营/治理/前瞻三类风险信号。', calls: 88, scenes: [] },
  { id: '4', name: '申请书结构解析', author: '孙老师', subject: '学术科研', desc: '解析基金申请书章节结构，对比已立项项目，输出改进建议。', calls: 38, scenes: ['课题申请书诊断'] },
  { id: '5', name: '创新点分析', author: '张老师', subject: '学术科研', desc: '对比目标论文与近期文献，分析创新点表述与支撑证据充分性。', calls: 29, scenes: ['论文计量方法鉴别', '课题申请书诊断'] },
  { id: '6', name: '量化因子筛选器', author: '李教授', subject: '量化投资', desc: '基于历史收益率构建多因子模型，筛选显著 alpha 因子组合。', calls: 52, scenes: ['量化因子研究'] },
  { id: '7', name: '持仓波动率分析', author: '王老师', subject: '资产管理', desc: '基于持仓数据计算各行业年化波动率，识别高风险持仓，生成减仓建议。', calls: 43, scenes: [] },
  { id: '8', name: '财务报表核查', author: '陈老师', subject: '会计审计', desc: '按表关键科目勾稽关系做动态检查，识别三表数据不一致项，输出异常清单。', calls: 61, scenes: ['企业财务风险分析'] },
  { id: '9', name: '信用风险评估', author: '刘老师', subject: '风险管理', desc: '基于财务指标构建信用评分模型，输出违约概率估计和风险等级。', calls: 35, scenes: [] },
]

const SUBJECT_TABS = ['全部', '公司金融', '量化投资', '资产管理', '风险管理', '学术科研', '会计审计']
const STATS = [
  { num: '12', label: '位老师已发布智能体' },
  { num: '847', label: '次分析任务已完成' },
  { num: '4', label: '个精选分析场景' },
  { num: '5', label: '个金融学科覆盖' },
]

// ── 子组件 ────────────────────────────────────────────────────

function FeaturedSceneCard({ scene, onUse }: { scene: FeaturedScene; onUse: () => void }) {
  const [hovered, setHovered] = useState(false)
  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        background: 'var(--surface)',
        border: `1px solid ${hovered ? 'var(--action-border)' : 'var(--border)'}`,
        borderRadius: 12,
        overflow: 'hidden',
        boxShadow: hovered ? '0 8px 32px rgba(23,73,196,0.10)' : '0 1px 4px rgba(11,46,92,0.05)',
        transition: 'border-color 0.2s, box-shadow 0.2s',
        display: 'flex', flexDirection: 'column' as const,
      }}
    >
      {/* 顶部色带 */}
      <div style={{ height: 4, background: 'var(--action)' }} />

      <div style={{ padding: '24px 28px', flex: 1, display: 'flex', flexDirection: 'column' as const, gap: 16 }}>
        {/* 标题区 */}
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
            <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--action)', background: 'var(--action-light)', padding: '2px 8px', borderRadius: 4, border: '1px solid var(--action-border)' }}>{scene.subject}</span>
            <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{scene.duration}</span>
            <span style={{ fontSize: 11, color: 'var(--text-muted)', marginLeft: 'auto' }}>▶ {scene.uses} 次使用</span>
          </div>
          <h3 style={{ fontSize: 20, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 6 }}>{scene.name}</h3>
          <p style={{ fontSize: 14, color: 'var(--action)', fontWeight: 500 }}>{scene.tagline}</p>
        </div>

        {/* 描述 */}
        <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.75 }}>{scene.desc}</p>

        {/* 分析流程 */}
        <div>
          <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' as const, letterSpacing: '0.15em', marginBottom: 10 }}>分析流程</div>
          <div style={{ display: 'flex', flexDirection: 'column' as const, gap: 6 }}>
            {scene.flow.map((step, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 10, fontSize: 13, color: 'var(--text-secondary)' }}>
                <span style={{ width: 20, height: 20, borderRadius: '50%', background: 'var(--action-light)', border: '1px solid var(--action-border)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 700, color: 'var(--action)', flexShrink: 0 }}>{i + 1}</span>
                <span style={{ lineHeight: 1.5, paddingTop: 2 }}>{step}</span>
              </div>
            ))}
          </div>
        </div>

        {/* 组成 Agent */}
        <div>
          <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' as const, letterSpacing: '0.15em', marginBottom: 8 }}>由以下智能体组成</div>
          <div style={{ display: 'flex', flexWrap: 'wrap' as const, gap: 6 }}>
            {scene.agents.map(a => (
              <span key={a.name} style={{ fontSize: 12, padding: '3px 10px', background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 5, color: 'var(--text-secondary)' }}>
                {a.name} <span style={{ color: 'var(--text-muted)' }}>· {a.author}</span>
              </span>
            ))}
          </div>
        </div>

        {/* 标签 */}
        <div style={{ display: 'flex', flexWrap: 'wrap' as const, gap: 5 }}>
          {scene.tags.map(t => (
            <span key={t} style={{ fontSize: 11, padding: '2px 7px', background: 'var(--bg)', color: 'var(--text-muted)', borderRadius: 3, border: '1px solid var(--border-light)' }}>{t}</span>
          ))}
        </div>
      </div>

      {/* 底部操作 */}
      <div style={{ padding: '16px 28px', borderTop: '1px solid var(--border-light)', background: 'var(--bg)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>登录后即可使用</span>
        <button
          onClick={onUse}
          style={{ padding: '8px 20px', background: 'var(--action)', color: '#fff', border: 'none', borderRadius: 7, fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit', display: 'flex', alignItems: 'center', gap: 6 }}
        >
          立即体验
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
        </button>
      </div>
    </div>
  )
}

function AgentMiniCard({ agent }: { agent: AgentCard }) {
  return (
    <CatalogCard
      title={agent.name}
      author={agent.author}
      subject={agent.subject}
      description={agent.desc}
      detail={agent.scenes.length > 0 ? `用于场景：${agent.scenes.join('、')}` : '暂未编入分析场景'}
      metric={`${agent.calls} 次调用`}
    />
  )
}

// ── 主页面 ────────────────────────────────────────────────────
export function Marketplace() {
  const navigate = useNavigate()
  // 筛选状态进 URL：可分享、可后退（审查文档 P1-3）
  const [searchParams, setSearchParams] = useSearchParams()
  const activeTab: 'scenes' | 'agents' = searchParams.get('tab') === 'agents' ? 'agents' : 'scenes'
  const activeSubject = searchParams.get('subject') ?? '全部'

  const setActiveTab = (key: 'scenes' | 'agents') => {
    const next = new URLSearchParams(searchParams)
    if (key === 'scenes') next.delete('tab')
    else next.set('tab', key)
    setSearchParams(next)
  }

  const setActiveSubject = (subject: string) => {
    const next = new URLSearchParams(searchParams)
    if (subject === '全部') next.delete('subject')
    else next.set('subject', subject)
    setSearchParams(next)
  }

  const filteredAgents = ALL_AGENTS.filter(a =>
    activeSubject === '全部' || a.subject === activeSubject
  )

  return (
    <div>
      {/* Hero 区 */}
      <section className="grid-bg" style={{ position: 'relative', overflow: 'hidden', borderBottom: '1px solid var(--border)' }}>
        <div style={{ maxWidth: 1300, margin: '0 auto', padding: '72px 80px 60px', position: 'relative' }}>
          <div style={{ maxWidth: 720 }}>
            <div style={{ fontSize: 10, fontFamily: "'JetBrains Mono', monospace", textTransform: 'uppercase' as const, letterSpacing: '0.3em', color: 'var(--text-muted)', marginBottom: 16 }}>
              // AGENT MARKETPLACE
            </div>
            <h1 style={{ fontSize: 40, fontWeight: 900, color: 'var(--text-primary)', lineHeight: 1.2, marginBottom: 16 }}>
              金融学院智能体市场
            </h1>
            <p style={{ fontSize: 16, color: 'var(--text-secondary)', lineHeight: 1.8, marginBottom: 12 }}>
              将老师们的方法论封装成可复用的分析场景。每个场景由一个或多个智能体协作完成，从数据到报告，全程自动化。
            </p>
            <p style={{ fontSize: 14, color: 'var(--text-muted)', lineHeight: 1.7 }}>
              教师提交自己的分析方法 → 平台封装为智能体 → 组合成完整分析场景 → 形成学院可持续积累的 Know-How 资产库
            </p>
          </div>

          {/* 数字统计 */}
          <div style={{ display: 'flex', gap: 40, marginTop: 40, paddingTop: 32, borderTop: '1px solid var(--border-light)' }}>
            {STATS.map(s => (
              <div key={s.label}>
                <div style={{ fontSize: 28, fontWeight: 800, color: 'var(--action)', fontFamily: "'JetBrains Mono', monospace", lineHeight: 1 }}>{s.num}</div>
                <div style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 6 }}>{s.label}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Tab 切换：精选场景 / 所有智能体 */}
      <section style={{ background: 'var(--surface)', borderBottom: '1px solid var(--border)', position: 'sticky', top: 56, zIndex: 50 }}>
        <div style={{ maxWidth: 1300, margin: '0 auto', padding: '0 80px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex' }}>
            {([['scenes', '精选分析场景'], ['agents', '所有智能体']] as const).map(([key, label]) => (
              <button
                key={key}
                onClick={() => setActiveTab(key)}
                style={{ padding: '16px 24px', fontSize: 14, fontWeight: activeTab === key ? 600 : 400, background: 'none', border: 'none', borderBottom: activeTab === key ? '2px solid var(--action)' : '2px solid transparent', marginBottom: -1, cursor: 'pointer', fontFamily: 'inherit', color: activeTab === key ? 'var(--action)' : 'var(--text-muted)', transition: 'color 0.15s' }}
              >{label}</button>
            ))}
          </div>
          <button
            onClick={() => navigate('/workspace')}
            style={{ padding: '8px 20px', background: 'var(--action)', color: '#fff', border: 'none', borderRadius: 7, fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}
          >进入工作台使用 →</button>
        </div>
      </section>

      {/* 精选场景 */}
      {activeTab === 'scenes' && (
        <section style={{ background: 'var(--bg)' }}>
          <div style={{ maxWidth: 1300, margin: '0 auto', padding: '48px 80px 72px' }}>
            <div style={{ marginBottom: 32 }}>
              <h2 style={{ fontSize: 26, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 8 }}>精选分析场景</h2>
              <p style={{ fontSize: 14, color: 'var(--text-muted)' }}>每个场景由多个智能体协作完成一类完整的金融分析任务，沉淀学院教研方法论</p>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 24 }}>
              {FEATURED_SCENES.map(scene => (
                <FeaturedSceneCard
                  key={scene.id}
                  scene={scene}
                  onUse={() => navigate('/workspace/scenarios')}
                />
              ))}
            </div>

            {/* 场景构成说明 */}
            <div style={{ marginTop: 48, background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12, padding: '32px 40px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 40, flexWrap: 'wrap' as const }}>
                <div style={{ flex: 1, minWidth: 280 }}>
                  <h3 style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 10 }}>场景是如何形成的？</h3>
                  <p style={{ fontSize: 14, color: 'var(--text-secondary)', lineHeight: 1.8 }}>
                    教师将自己的分析方法和经验封装成智能体，经平台审核发布。当一个或多个智能体能够解决一类完整的分析任务时，管理员将其组合为「场景」，进入场景库供所有师生一键使用。
                  </p>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexShrink: 0 }}>
                  {['教师方法论', '封装为 Agent', '组合成场景', '学院 Know-How'].map((s, i, arr) => (
                    <div key={s} style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                      <div style={{ textAlign: 'center' as const }}>
                        <div style={{ width: 44, height: 44, borderRadius: '50%', background: 'var(--action-light)', border: '1px solid var(--action-border)', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 8px', fontSize: 18 }}>
                          {['💡', '🤖', '🎯', '📚'][i]}
                        </div>
                        <div style={{ fontSize: 12, color: 'var(--text-secondary)', whiteSpace: 'nowrap' as const }}>{s}</div>
                      </div>
                      {i < arr.length - 1 && <span style={{ color: 'var(--border)', fontSize: 20, marginBottom: 20 }}>→</span>}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </section>
      )}

      {/* 所有智能体 */}
      {activeTab === 'agents' && (
        <section style={{ background: 'var(--bg)' }}>
          <div style={{ maxWidth: 1300, margin: '0 auto', padding: '48px 80px 72px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 28 }}>
              <div>
                <h2 style={{ fontSize: 26, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 8 }}>所有智能体</h2>
                <p style={{ fontSize: 14, color: 'var(--text-muted)' }}>由学院老师发布，可独立调用或组合成场景</p>
              </div>
              {/* 学科筛选 */}
              <div style={{ display: 'flex', gap: 6 }}>
                {SUBJECT_TABS.map(s => (
                  <button
                    key={s}
                    onClick={() => setActiveSubject(s)}
                    style={{ padding: '6px 14px', borderRadius: 20, border: `1px solid ${activeSubject === s ? 'var(--action)' : 'var(--border)'}`, background: activeSubject === s ? 'var(--action)' : 'var(--surface)', color: activeSubject === s ? '#fff' : 'var(--text-secondary)', fontSize: 12, fontWeight: activeSubject === s ? 600 : 400, cursor: 'pointer', fontFamily: 'inherit', transition: 'background 0.15s, color 0.15s, border-color 0.15s' }}
                  >{s}</button>
                ))}
              </div>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
              {filteredAgents.map(agent => <AgentMiniCard key={agent.id} agent={agent} />)}
            </div>

            {/* CTA */}
            <div style={{ marginTop: 40, textAlign: 'center' as const }}>
              <p style={{ fontSize: 14, color: 'var(--text-muted)', marginBottom: 16 }}>你也有方法论想分享给学院？</p>
              <button onClick={() => navigate('/workspace/my-agents/create')} style={{ padding: '10px 28px', background: 'var(--action)', color: '#fff', border: 'none', borderRadius: 8, fontSize: 14, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>
                发布你的智能体
              </button>
            </div>
          </div>
        </section>
      )}
    </div>
  )
}
