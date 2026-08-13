import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { CatalogCard, CatalogControls } from '../components/Catalog'

interface Agent {
  id: string; name: string; author: string; subject: string
  desc: string; dataNeeded: string; calls: number; version: string
  kind?: '系统提示词' | '独立部署 MCP'
  prompt: string
}

const MOCK_AGENTS: Agent[] = [
  { id: '1', name: '企业财务异常检测', author: '张老师', subject: '公司金融', desc: '对报表关键科目进行稽核式比率检查，识别应收账款、存货、流动比率等指标的异常，输出带证据的异常项清单。', dataNeeded: '财报 Excel / CSV', calls: 96, version: 'v1.2', prompt: '你是一位专业的财务分析师，擅长识别财务报表中的异常信号。\n\n请按以下步骤分析：\n1. 读取财务报表数据，了解科目结构\n2. 计算流动比率、速动比率、资产负债率等关键指标\n3. 与行业平均水平对比，识别偏离超过 1.5 个标准差的指标\n4. 输出异常项清单...' },
  { id: '2', name: '计量方法识别', author: '赵老师', subject: '学术科研', desc: '识别论文使用的识别策略与计量方法（DID/RDD/IV），提取模型设定与稳健性检验清单，指出潜在缺陷。', dataNeeded: '论文 PDF', calls: 64, version: 'v1.1', prompt: '你是一位计量经济学专家。\n\n请对上传的论文执行以下分析：\n1. 识别核心识别策略（DID / RDD / IV / 自然实验等）\n2. 提取模型设定，包括控制变量选取逻辑\n3. 列出稳健性检验方法\n4. 指出可能的识别威胁...' },
  { id: '3', name: '公告语义分析', author: '平台 · 公共', subject: '风险管理', desc: '对上市公司公告进行语义分析，识别经营/治理/前瞻三类风险信号，输出风险信号摘要与原文定位。', dataNeeded: '公告文本 / PDF', calls: 88, version: 'v1.0', kind: '独立部署 MCP', prompt: '你是一位专业的证券分析师，擅长解读上市公司公告。\n\n请对上传的公告文本：\n1. 识别经营类风险信号（业绩下滑、客户集中、合同纠纷）\n2. 识别治理类风险信号（高管变动、关联交易、股权质押）\n3. 识别前瞻性信号（扩产计划、并购意图）...' },
  { id: '4', name: '申请书结构解析', author: '孙老师', subject: '学术科研', desc: '解析国家自然科学基金申请书的章节结构、立项依据与研究方案组织方式，对比同领域已立项项目给出改进建议。', dataNeeded: '申请书 PDF', calls: 38, version: 'v1.0', prompt: '你是一位经验丰富的科研项目评审专家。\n\n请对上传的申请书进行以下诊断：\n1. 检查立项依据的论证逻辑\n2. 核查研究内容与研究目标的对应关系\n3. 比对研究方案的技术路线\n4. 输出差距清单...' },
  { id: '5', name: '创新点分析', author: '张老师', subject: '学术科研', desc: '对比目标文本与领域近期文献，分析创新点的表述方式与支撑证据是否充分，输出创新点强弱评估。', dataNeeded: '论文 PDF', calls: 29, version: 'v1.0', prompt: '你是一位金融学领域的学术审稿人。\n\n请对目标论文的创新点进行分析：\n1. 提取作者自述的创新点\n2. 在论文正文中验证每条创新点是否有充分论证\n3. 与近三年同方向文献对比...' },
  { id: '6', name: '财务报表核查', author: '陈老师', subject: '会计审计', desc: '按表关键科目衔接与勾稽关系做动态检查，识别三表数据不一致项，输出异常项清单与修正建议。', dataNeeded: '财报 CSV / Excel', calls: 61, version: 'v1.0', prompt: '你是一位注册会计师，专注于财务报表的内部勾稽核查。\n\n请对上传的财务报表：\n1. 检查资产负债表、利润表、现金流量表三表勾稽关系\n2. 识别净利润与经营现金流的偏差\n3. 检查关键科目环比异常变动...' },
  { id: '7', name: '量化因子筛选器', author: '李教授', subject: '量化投资', desc: '基于历史收益率数据构建多因子模型，筛选具有显著 alpha 的因子组合，输出因子暴露与显著性报告。', dataNeeded: '股票日 K 数据 CSV', calls: 52, version: 'v1.0', prompt: '你是一位量化研究员。\n\n请基于上传的股票数据：\n1. 计算常见因子值（动量、市值、市盈率等）\n2. 使用 Fama-French 框架进行因子回归\n3. 检验因子的 alpha 显著性（t 检验，p < 0.05）\n4. 输出显著因子列表及其因子暴露...' },
  { id: '8', name: '持仓波动率分析', author: '王老师', subject: '资产管理', desc: '基于持仓数据计算各行业年化波动率，识别高风险持仓，生成组合风险热力图与减仓建议。', dataNeeded: '持仓 CSV（含行业分类）', calls: 43, version: 'v1.0', prompt: '你是一位专业的组合管理分析师。\n\n请对上传的持仓数据：\n1. 按行业分组计算加权年化波动率\n2. 识别超过阈值的高波动率行业\n3. 给出降低组合整体风险的减仓建议...' },
  { id: '9', name: '信用风险评估', author: '刘老师', subject: '风险管理', desc: '基于企业财务指标和行业数据，构建信用评分模型，输出违约概率估计和风险等级。', dataNeeded: '企业财务数据 CSV', calls: 35, version: 'v1.0', prompt: '你是一位信用分析师。\n\n请对上传的财务数据：\n1. 计算偿债能力指标（流动比率、速动比率、利息保障倍数）\n2. 计算盈利能力指标（ROE、ROA、EBITDA 利润率）\n3. 基于 Altman Z-Score 模型估计违约概率...' },
]

function AgentCard({ agent, onDetail, onUse }: { agent: Agent; onDetail: () => void; onUse: () => void }) {
  return (
    <CatalogCard
      title={agent.name}
      version={agent.version}
      author={agent.author}
      subject={agent.subject}
      description={agent.desc}
      detail={`需要：${agent.dataNeeded}`}
      badges={[agent.kind ?? '系统提示词']}
      metric={`${agent.calls} 次调用`}
      secondaryAction={{ label: '查看详情', onClick: onDetail }}
      primaryAction={{ label: '使用此 Agent', onClick: onUse }}
    />
  )
}

// 金融学院导向的分类体系
const SUBJECTS_FILTER = [
  { key: '全部',     label: '全部' },
  { key: '公司金融', label: '公司金融' },
  { key: '量化投资', label: '量化投资' },
  { key: '资产管理', label: '资产管理' },
  { key: '风险管理', label: '风险管理' },
  { key: '学术科研', label: '学术科研' },
  { key: '会计审计', label: '会计审计' },
  { key: '其他',     label: '其他' },
]

const PAGE_SIZE = 6

export function AgentPlaza() {
  const navigate = useNavigate()
  const [activeSubject, setActiveSubject] = useState('全部')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [detailAgent, setDetailAgent] = useState<Agent | null>(null)

  const filtered = MOCK_AGENTS
    .filter(a => {
      const matchSubject = activeSubject === '全部' || a.subject === activeSubject
      const matchSearch = !search || a.name.includes(search) || a.desc.includes(search) || a.author.includes(search)
      return matchSubject && matchSearch
    })
    .sort((a, b) => b.calls - a.calls)

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const paged = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  // 切筛选/搜索时重置到第1页
  const handleSubject = (s: string) => { setActiveSubject(s); setPage(1) }
  const handleSearch = (v: string) => { setSearch(v); setPage(1) }

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
    <div style={{ flex: 1, overflowY: 'auto', background: 'var(--bg)' }}>
      {/* 页头 */}
      <div style={{ padding: '28px 36px 0' }}>
        <div style={{ fontSize: 10, fontFamily: "'JetBrains Mono', monospace", textTransform: 'uppercase' as const, letterSpacing: '0.3em', color: 'var(--text-muted)', marginBottom: 6 }}>// AGENT PLAZA</div>
        <h1 style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>智能体广场</h1>
        <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>浏览并使用学院老师发布的分析智能体，共 {MOCK_AGENTS.length} 个</p>
      </div>

      <CatalogControls
        search={search}
        onSearch={handleSearch}
        placeholder="搜索名称、描述或作者..."
        filters={SUBJECTS_FILTER}
        activeFilter={activeSubject}
        onFilter={handleSubject}
      />

      {/* 卡片网格 */}
      <div style={{ padding: '0 36px' }}>
        {paged.length === 0 ? (
          <div style={{ padding: '60px 0', textAlign: 'center' as const, color: 'var(--text-muted)', fontSize: 14 }}>
            {search ? `未找到与「${search}」相关的智能体` : '该分类暂无智能体'}
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
            {paged.map(agent => (
              <AgentCard key={agent.id} agent={agent} onDetail={() => setDetailAgent(agent)} onUse={() => handleUse(agent)} />
            ))}
          </div>
        )}

        {/* 分页 */}
        {totalPages > 1 && (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, padding: '28px 0 32px' }}>
            <button
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={page === 1}
              style={{ width: 32, height: 32, display: 'flex', alignItems: 'center', justifyContent: 'center', border: '1px solid var(--border)', borderRadius: 6, background: 'var(--surface)', color: page === 1 ? 'var(--text-muted)' : 'var(--text-secondary)', cursor: page === 1 ? 'default' : 'pointer', fontSize: 14 }}
            >‹</button>
            {Array.from({ length: totalPages }, (_, i) => i + 1).map(p => (
              <button
                key={p}
                onClick={() => setPage(p)}
                style={{ width: 32, height: 32, display: 'flex', alignItems: 'center', justifyContent: 'center', border: '1px solid ' + (page === p ? 'var(--action)' : 'var(--border)'), borderRadius: 6, background: page === p ? 'var(--action)' : 'var(--surface)', color: page === p ? '#fff' : 'var(--text-secondary)', cursor: 'pointer', fontSize: 13, fontWeight: page === p ? 600 : 400 }}
              >{p}</button>
            ))}
            <button
              onClick={() => setPage(p => Math.min(totalPages, p + 1))}
              disabled={page === totalPages}
              style={{ width: 32, height: 32, display: 'flex', alignItems: 'center', justifyContent: 'center', border: '1px solid var(--border)', borderRadius: 6, background: 'var(--surface)', color: page === totalPages ? 'var(--text-muted)' : 'var(--text-secondary)', cursor: page === totalPages ? 'default' : 'pointer', fontSize: 14 }}
            >›</button>
            <span style={{ fontSize: 12, color: 'var(--text-muted)', marginLeft: 8 }}>共 {filtered.length} 个</span>
          </div>
        )}
        {totalPages <= 1 && filtered.length > 0 && (
          <div style={{ padding: '20px 0 32px', textAlign: 'center' as const }}>
            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>共 {filtered.length} 个智能体</span>
          </div>
        )}
      </div>

      {/* 详情侧抽屉 */}
      {detailAgent && (
        <>
          <div onClick={() => setDetailAgent(null)} style={{ position: 'fixed', inset: 0, background: 'rgba(13,24,41,0.3)', zIndex: 200 }} />
          <div style={{ position: 'fixed', top: 0, right: 0, bottom: 0, width: 460, background: 'var(--surface)', borderLeft: '1px solid var(--border)', zIndex: 201, display: 'flex', flexDirection: 'column', boxShadow: '-8px 0 24px rgba(11,46,92,0.12)' }}>
            <div style={{ padding: '20px 24px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div>
                <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: 6 }}>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" style={{ color: 'var(--action)', flexShrink: 0 }}><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M9 21V9"/></svg>
                  {detailAgent.name}
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 3 }}>{detailAgent.author} · {detailAgent.subject} · {detailAgent.version}</div>
              </div>
              <button onClick={() => setDetailAgent(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', fontSize: 20, lineHeight: 1 }}>×</button>
            </div>
            <div style={{ flex: 1, overflowY: 'auto', padding: '20px 24px' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20, padding: '12px 16px', background: 'var(--bg)', borderRadius: 8, fontSize: 12, color: 'var(--text-muted)' }}>
                <span>配置类型：<strong style={{ color: 'var(--text-secondary)' }}>{detailAgent.kind ?? '系统提示词'}</strong></span>
                <span>{detailAgent.calls} 次使用</span>
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
            <div style={{ marginBottom: 12, color: 'var(--text-muted)' }}>
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="12" cy="8" r="4"/><path d="M20 21a8 8 0 1 0-16 0"/></svg>
            </div>
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
