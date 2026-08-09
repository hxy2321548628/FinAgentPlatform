import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

interface Agent {
  id: string; name: string; author: string; subject: string
  desc: string; dataNeeded: string; calls: number; rating: number; version: string
  ratingDist: number[]  // 5星到1星的评分人数
  prompt: string        // 系统提示词摘要（前200字）
}

const SUBJECTS_FILTER = ['全部', '金融', '会计', '经济', '管理']

const MOCK_AGENTS: Agent[] = [
  { id: '1', name: '企业财务异常检测', author: '张老师', subject: '金融', desc: '对报表关键科目进行稽核式比率检查，识别应收账款、存货、流动比率等指标的异常，输出带证据的异常项清单。', dataNeeded: '财报 Excel / CSV', calls: 96, rating: 4.8, version: 'v1.2', ratingDist: [78, 12, 4, 2, 0], prompt: '你是一位专业的财务分析师，擅长识别财务报表中的异常信号。\n\n请按以下步骤分析：\n1. 读取财务报表数据，了解科目结构\n2. 计算流动比率、速动比率、资产负债率等关键指标\n3. 与行业平均水平对比，识别偏离超过 1.5 个标准差的指标\n4. 输出异常项清单...' },
  { id: '2', name: '计量方法识别', author: '赵老师', subject: '经济', desc: '识别论文使用的识别策略与计量方法（DID/RDD/IV），提取模型设定与稳健性检验清单，指出潜在缺陷。', dataNeeded: '论文 PDF', calls: 64, rating: 4.7, version: 'v1.1', ratingDist: [52, 8, 3, 1, 0], prompt: '你是一位计量经济学专家。\n\n请对上传的论文执行以下分析：\n1. 识别核心识别策略（DID / RDD / IV / 自然实验等）\n2. 提取模型设定，包括控制变量选取逻辑\n3. 列出稳健性检验方法\n4. 指出可能的识别威胁...' },
  { id: '3', name: '公告语义分析', author: '平台 · 公共', subject: '金融', desc: '对上市公司公告进行语义分析，识别经营/治理/前瞻三类风险信号，输出风险信号摘要与原文定位。', dataNeeded: '公告文本 / PDF', calls: 88, rating: 4.6, version: 'v1.0', ratingDist: [63, 18, 5, 2, 0], prompt: '你是一位专业的证券分析师，擅长解读上市公司公告。\n\n请对上传的公告文本：\n1. 识别经营类风险信号（业绩下滑、客户集中、合同纠纷）\n2. 识别治理类风险信号（高管变动、关联交易、股权质押）\n3. 识别前瞻性信号（扩产计划、并购意图）...' },
  { id: '4', name: '申请书结构解析', author: '孙老师', subject: '管理', desc: '解析国家自然科学基金申请书的章节结构、立项依据与研究方案组织方式，对比同领域已立项项目给出改进建议。', dataNeeded: '申请书 PDF', calls: 38, rating: 4.5, version: 'v1.0', ratingDist: [28, 7, 2, 1, 0], prompt: '你是一位经验丰富的科研项目评审专家。\n\n请对上传的申请书进行以下诊断：\n1. 检查立项依据的论证逻辑\n2. 核查研究内容与研究目标的对应关系\n3. 比对研究方案的技术路线\n4. 输出差距清单...' },
  { id: '5', name: '创新点分析', author: '张老师', subject: '金融', desc: '对比目标文本与领域近期文献，分析创新点的表述方式与支撑证据是否充分，输出创新点强弱评估。', dataNeeded: '论文 PDF', calls: 29, rating: 4.4, version: 'v1.0', ratingDist: [20, 6, 2, 1, 0], prompt: '你是一位金融学领域的学术审稿人。\n\n请对目标论文的创新点进行分析：\n1. 提取作者自述的创新点\n2. 在论文正文中验证每条创新点是否有充分论证\n3. 与近三年同方向文献对比...' },
  { id: '6', name: '财务报表核查', author: '陈老师', subject: '会计', desc: '按表关键科目衔接与勾稽关系做动态检查，识别三表数据不一致项，输出异常项清单与修正建议。', dataNeeded: '财报 CSV / Excel', calls: 61, rating: 4.6, version: 'v1.0', ratingDist: [48, 10, 2, 1, 0], prompt: '你是一位注册会计师，专注于财务报表的内部勾稽核查。\n\n请对上传的财务报表：\n1. 检查资产负债表、利润表、现金流量表三表勾稽关系\n2. 识别净利润与经营现金流的偏差\n3. 检查关键科目环比异常变动...' },
]

function RatingBar({ dist, total }: { dist: number[]; total: number }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column' as const, gap: 4 }}>
      {dist.map((count, i) => {
        const star = 5 - i
        const pct = total > 0 ? Math.round(count / total * 100) : 0
        return (
          <div key={star} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 11 }}>
            <span style={{ color: 'var(--text-muted)', width: 14, textAlign: 'right' as const }}>{star}★</span>
            <div style={{ flex: 1, height: 5, background: 'var(--border-light)', borderRadius: 3, overflow: 'hidden' }}>
              <div style={{ height: '100%', width: `${pct}%`, background: pct > 0 ? '#F59E0B' : 'transparent', borderRadius: 3 }} />
            </div>
            <span style={{ color: 'var(--text-muted)', width: 28, textAlign: 'right' as const }}>{count}</span>
          </div>
        )
      })}
    </div>
  )
}

function AgentCard({ agent, onDetail, onUse }: { agent: Agent; onDetail: () => void; onUse: () => void }) {
  const [hovered, setHovered] = useState(false)
  return (
    <div onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)} style={{ background: 'var(--surface)', border: '1px solid ' + (hovered ? 'var(--action-border)' : 'var(--border)'), borderRadius: 10, padding: 24, display: 'flex', flexDirection: 'column' as const, gap: 10, boxShadow: hovered ? '0 4px 16px rgba(23,73,196,0.08)' : 'none', transition: 'border-color 0.2s, box-shadow 0.2s' }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
        <button onClick={onDetail} style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit', padding: 0, textAlign: 'left' as const }}>📊 {agent.name}</button>
        <span style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: "'JetBrains Mono', monospace", flexShrink: 0, marginLeft: 8 }}>{agent.version}</span>
      </div>
      <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{agent.author} · {agent.subject}</div>
      <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.65, flex: 1 }}>{agent.desc}</p>
      <div style={{ fontSize: 12, color: 'var(--text-muted)', padding: '8px 0', borderTop: '1px solid var(--border-light)', borderBottom: '1px solid var(--border-light)' }}>需要：{agent.dataNeeded}</div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: 12, color: 'var(--text-muted)' }}>
        <span>▶ {agent.calls} 次调用</span>
        <span style={{ color: '#F59E0B', fontWeight: 600 }}>⭐ {agent.rating}</span>
      </div>
      <div style={{ display: 'flex', gap: 8 }}>
        <button onClick={onDetail} style={{ flex: 1, padding: '7px 0', background: 'transparent', color: 'var(--action)', border: '1px solid var(--action-border)', borderRadius: 7, fontSize: 13, cursor: 'pointer', fontFamily: 'inherit' }}>查看详情</button>
        <button onClick={onUse} style={{ flex: 1, padding: '7px 0', background: 'var(--action)', color: '#fff', border: 'none', borderRadius: 7, fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>使用此 Agent</button>
      </div>
    </div>
  )
}

export function AgentPlaza() {
  const navigate = useNavigate()
  const [activeSubject, setActiveSubject] = useState('全部')
  const [sortBy, setSortBy] = useState<'calls' | 'rating'>('calls')
  const [detailAgent, setDetailAgent] = useState<Agent | null>(null)

  const filtered = MOCK_AGENTS.filter(a => activeSubject === '全部' || a.subject === activeSubject).sort((a, b) => b[sortBy] - a[sortBy])

  const handleUse = (agent: Agent) => {
    navigate('/workspace/chat', {
      state: {
        agentId: agent.id,
        agentName: agent.name,
        agentAuthor: agent.author,
        agentDataNeeded: agent.dataNeeded,
      }
    })
  }
  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '32px 36px', background: 'var(--bg)' }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 28 }}>
        <div>
          <div style={{ fontSize: 10, fontFamily: "'JetBrains Mono', monospace", textTransform: 'uppercase' as const, letterSpacing: '0.3em', color: 'var(--text-muted)', marginBottom: 6 }}>// AGENT PLAZA</div>
          <h1 style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>智能体广场</h1>
          <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>浏览并使用其他老师发布的分析智能体</p>
        </div>
        <button onClick={() => navigate('/workspace/agents/publish')} style={{ padding: '9px 20px', background: 'var(--action)', color: '#fff', border: 'none', borderRadius: 7, fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit', flexShrink: 0 }}>+ 发布我的智能体</button>
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
        {filtered.map(agent => <AgentCard key={agent.id} agent={agent} onDetail={() => setDetailAgent(agent)} onUse={() => handleUse(agent)} />)}
      </div>

      {/* 详情侧抽屉 */}
      {detailAgent && (
        <>
          <div onClick={() => setDetailAgent(null)} style={{ position: 'fixed', inset: 0, background: 'rgba(13,24,41,0.3)', zIndex: 200 }} />
          <div style={{ position: 'fixed', top: 0, right: 0, bottom: 0, width: 460, background: 'var(--surface)', borderLeft: '1px solid var(--border)', zIndex: 201, display: 'flex', flexDirection: 'column', boxShadow: '-8px 0 24px rgba(11,46,92,0.12)' }}>
            <div style={{ padding: '20px 24px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div>
                <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)' }}>📊 {detailAgent.name}</div>
                <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 3 }}>{detailAgent.author} · {detailAgent.subject} · {detailAgent.version}</div>
              </div>
              <button onClick={() => setDetailAgent(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', fontSize: 20, lineHeight: 1 }}>×</button>
            </div>
            <div style={{ flex: 1, overflowY: 'auto', padding: '20px 24px' }}>
              {/* 评分区 */}
              <div style={{ display: 'flex', gap: 24, marginBottom: 20, padding: '14px 16px', background: 'var(--bg)', borderRadius: 8 }}>
                <div style={{ textAlign: 'center' as const }}>
                  <div style={{ fontSize: 36, fontWeight: 800, color: '#F59E0B', fontFamily: "'JetBrains Mono', monospace", lineHeight: 1 }}>{detailAgent.rating}</div>
                  <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>综合评分</div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>{detailAgent.calls} 次使用</div>
                </div>
                <div style={{ flex: 1 }}>
                  <RatingBar dist={detailAgent.ratingDist} total={detailAgent.calls} />
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 8 }}>
                    评分来源：每次对话结束后用户自愿评价
                  </div>
                </div>
              </div>

              {/* 描述 */}
              <div style={{ marginBottom: 16 }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' as const, letterSpacing: '0.1em', marginBottom: 8 }}>功能描述</div>
                <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.75 }}>{detailAgent.desc}</div>
              </div>

              {/* 所需数据 */}
              <div style={{ marginBottom: 16 }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' as const, letterSpacing: '0.1em', marginBottom: 8 }}>所需数据</div>
                <div style={{ fontSize: 13, color: 'var(--text-secondary)', background: 'var(--bg)', padding: '8px 12px', borderRadius: 6, fontFamily: "'JetBrains Mono', monospace" }}>{detailAgent.dataNeeded}</div>
              </div>

              {/* 系统提示词摘要 */}
              <div style={{ marginBottom: 20 }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' as const, letterSpacing: '0.1em', marginBottom: 8 }}>分析方法摘要</div>
                <div style={{ background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 6, padding: '12px 14px', fontSize: 12, fontFamily: "'JetBrains Mono', monospace", color: 'var(--text-secondary)', lineHeight: 1.8, whiteSpace: 'pre-wrap' as const }}>
                  {detailAgent.prompt}
                  <span style={{ color: 'var(--text-muted)' }}> ...</span>
                </div>
              </div>
            </div>
            <div style={{ padding: '16px 24px', borderTop: '1px solid var(--border)' }}>
              <button onClick={() => { setDetailAgent(null); handleUse(detailAgent) }} style={{ width: '100%', padding: '11px 0', background: 'var(--action)', color: '#fff', border: 'none', borderRadius: 8, fontSize: 14, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>
                使用此 Agent 开始分析 →
              </button>
            </div>
          </div>
        </>
      )}
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

// 已创建状态的 agent（联调时从 API 获取），此处 mock
const MOCK_CREATED_AGENTS = [
  { id: '3', name: '股价动量因子筛选', subject: '金融学' },
  { id: '4', name: '财报 OCR 解析', subject: '会计学' },
]

export function PublishAgent() {
  const navigate = useNavigate()
  const [selectedId, setSelectedId] = useState('')
  const [desc, setDesc] = useState('')
  const [dataNeeded, setDataNeeded] = useState('')
  const [submitted, setSubmitted] = useState(false)

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedId || !desc.trim()) return
    setSubmitted(true)
    setTimeout(() => navigate('/workspace/my-agents'), 1500)
  }

  if (submitted) {
    return (
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--bg)' }}>
        <div style={{ textAlign: 'center' as const }}>
          <div style={{ fontSize: 40, marginBottom: 16 }}>✓</div>
          <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 8 }}>已提交审核</div>
          <div style={{ fontSize: 14, color: 'var(--text-muted)' }}>审核通过后智能体将出现在广场，跳转至「我的智能体」...</div>
        </div>
      </div>
    )
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '32px 36px', background: 'var(--bg)' }}>
      <div style={{ maxWidth: 680, margin: '0 auto' }}>
        <div style={{ marginBottom: 28 }}>
          <div style={{ fontSize: 10, fontFamily: "'JetBrains Mono', monospace", textTransform: 'uppercase' as const, letterSpacing: '0.3em', color: 'var(--text-muted)', marginBottom: 6 }}>// PUBLISH AGENT</div>
          <h1 style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>发布到智能体广场</h1>
          <p style={{ fontSize: 13, color: 'var(--text-muted)', lineHeight: 1.6 }}>
            选择一个「已创建」状态的智能体，填写广场展示信息后提交审核。审核通过后对所有用户可见。
          </p>
        </div>

        {MOCK_CREATED_AGENTS.length === 0 ? (
          <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, padding: '48px 24px', textAlign: 'center' as const }}>
            <div style={{ fontSize: 32, marginBottom: 12 }}>🤖</div>
            <div style={{ fontSize: 14, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 8 }}>暂无可发布的智能体</div>
            <div style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 20 }}>需要先在「我的智能体」中创建并保存智能体</div>
            <button onClick={() => navigate('/workspace/my-agents/create')} style={{ padding: '8px 20px', background: 'var(--action)', color: '#fff', border: 'none', borderRadius: 7, fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>去创建智能体</button>
          </div>
        ) : (
          <form onSubmit={handleSubmit}>
            <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, padding: 24, marginBottom: 16 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 20 }}>选择智能体</div>
              <FormField label="选择要发布的智能体" required hint="只有「已创建」状态的智能体可以申请发布到广场">
                <select value={selectedId} onChange={e => setSelectedId(e.target.value)} style={{ ...inputStyle, cursor: 'pointer', color: selectedId ? 'var(--text-primary)' : 'var(--text-muted)' }}>
                  <option value="">-- 请选择 --</option>
                  {MOCK_CREATED_AGENTS.map(a => (
                    <option key={a.id} value={a.id}>{a.name}（{a.subject}）</option>
                  ))}
                </select>
              </FormField>
            </div>

            <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, padding: 24, marginBottom: 24 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 4 }}>广场展示信息</div>
              <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 20, lineHeight: 1.6 }}>这些信息用于广场卡片展示，与智能体内部的系统提示词相互独立</div>
              <FormField label="功能描述" required hint="简短说明这个智能体能解决什么问题，200 字以内">
                <textarea value={desc} onChange={e => setDesc(e.target.value)} placeholder="如：对财报关键科目进行稽核式比率检查，识别异常项并输出清单" style={{ ...inputStyle, minHeight: 90, resize: 'vertical' as const }} maxLength={200} />
              </FormField>
              <FormField label="所需数据" hint="告知使用者需要上传什么格式的文件">
                <input value={dataNeeded} onChange={e => setDataNeeded(e.target.value)} placeholder="如：财报 CSV / Excel" style={inputStyle} />
              </FormField>
            </div>

            <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
              <button type="button" onClick={() => navigate('/workspace/agents')} style={{ padding: '9px 20px', background: 'var(--surface)', color: 'var(--text-secondary)', border: '1px solid var(--border)', borderRadius: 7, fontSize: 13, cursor: 'pointer', fontFamily: 'inherit' }}>取消</button>
              <button type="submit" style={{ padding: '9px 20px', background: 'var(--action)', color: '#fff', border: 'none', borderRadius: 7, fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>提交审核</button>
            </div>
          </form>
        )}
      </div>
    </div>
  )
}
