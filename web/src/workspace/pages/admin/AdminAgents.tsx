import { useState } from 'react'

type AgentType = 'prompt' | 'deployed'

interface PendingAgent {
  id: string; name: string; author: string; subject: string
  type: AgentType
  desc: string; dataNeeded: string; prompt: string; submittedAt: string
}

const MOCK_PENDING_AGENTS: PendingAgent[] = [
  {
    id: '1', name: '企业财务异常检测 v2', author: '张老师', subject: '金融学', type: 'prompt',
    desc: '对报表关键科目进行稽核式比率检查，识别异常项并输出清单。升级版增加了行业对比维度。',
    dataNeeded: '财报 Excel / CSV',
    prompt: '你是一位专业的财务分析师，擅长识别财务报表中的异常信号。\n\n请按以下步骤分析：\n1. 读取财务报表数据\n2. 计算流动比率、速动比率、资产负债率等关键指标\n3. 与行业平均水平对比，识别偏离超过 1.5 个标准差的指标\n4. 输出异常项清单，每项注明具体数值和判断依据\n5. 给出综合风险评级（高/中/低）',
    submittedAt: '2026-08-09 14:22',
  },
  {
    id: '2', name: '量化因子筛选器', author: '李教授', subject: '金融学', type: 'prompt',
    desc: '基于历史收益率数据构建多因子模型，筛选具有显著 alpha 的因子组合。',
    dataNeeded: '股票日 K 数据 CSV',
    prompt: '你是一位量化研究员。\n\n请基于上传的股票数据：\n1. 计算常见因子值（动量、市值、市盈率等）\n2. 使用 Fama-French 框架进行因子回归\n3. 检验因子的 alpha 显著性（t 检验，p < 0.05）\n4. 输出显著因子列表及其因子暴露',
    submittedAt: '2026-08-08 09:15',
  },
  {
    id: '3', name: '计量方法鉴别器', author: '赵老师', subject: '经济学', type: 'prompt',
    desc: '识别论文中使用的因果推断策略（DID/RDD/IV），提取稳健性检验方法并标注潜在缺陷。',
    dataNeeded: '论文 PDF',
    prompt: '你是一位计量经济学专家。\n\n请对上传的论文执行以下分析：\n1. 识别核心识别策略（DID / RDD / IV / 自然实验等）\n2. 提取模型设定，包括控制变量选取逻辑\n3. 列出稳健性检验方法（平行趋势检验、带宽敏感性等）\n4. 指出可能的识别威胁与局限性\n5. 输出结构化评估报告',
    submittedAt: '2026-08-09 10:48',
  },
  {
    id: '4', name: '财报实时爬取 Agent', author: '孙老师', subject: '会计学', type: 'deployed',
    desc: '定期爬取 A 股上市公司季度财报，结构化存入数据库，供财务分析类 agent 直接调用。需要独立部署爬虫服务与数据库。',
    dataNeeded: '无需上传，自动爬取',
    prompt: '（独立部署 Agent，无系统提示词）\n\n本 Agent 通过定时任务爬取巨潮资讯网、上交所、深交所三大数据源的财报披露，解析 PDF 财报并抽取关键字段存入 PostgreSQL，供平台其他 agent 通过统一接口查询。\n\n需要：\n- Python 爬虫服务（部署在内网）\n- PostgreSQL 数据库\n- 定时调度器（如 APScheduler）',
    submittedAt: '2026-08-09 16:05',
  },
  {
    id: '5', name: '课题申请书诊断', author: '陈老师', subject: '管理科学', type: 'prompt',
    desc: '对国家自然科学基金申请书进行结构诊断，对比同领域已立项项目，识别差距并给出修改建议。',
    dataNeeded: '申请书 PDF',
    prompt: '你是一位经验丰富的科研项目评审专家。\n\n请对上传的申请书进行以下诊断：\n1. 检查立项依据的论证逻辑：政策背景 → 研究缺口 → 本研究切入点是否成立\n2. 核查研究内容与研究目标的对应关系，是否存在目标虚高或内容不足\n3. 比对研究方案的技术路线是否清晰、创新点是否有文献支撑\n4. 输出差距清单，每条附具体修改建议，并引用同类已立项项目的处理方式',
    submittedAt: '2026-08-09 11:20',
  },
]

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: 'flex', gap: 16, marginBottom: 12, alignItems: 'flex-start' }}>
      <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' as const, letterSpacing: '0.1em', width: 70, flexShrink: 0, paddingTop: 1 }}>{label}</div>
      <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{value}</div>
    </div>
  )
}

export function AdminAgents() {
  const [agents, setAgents] = useState(MOCK_PENDING_AGENTS)
  const [detailId, setDetailId] = useState<string | null>(null)
  const [rejectReason, setRejectReason] = useState('')
  const detailAgent = agents.find(a => a.id === detailId)

  const handleApprove = (id: string) => { setAgents(prev => prev.filter(a => a.id !== id)); if (detailId === id) setDetailId(null) }
  const handleReject = (id: string) => { setAgents(prev => prev.filter(a => a.id !== id)); if (detailId === id) { setDetailId(null); setRejectReason('') } }

  const thStyle: React.CSSProperties = { padding: '10px 16px', textAlign: 'left', fontSize: 11, color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em', borderBottom: '1px solid var(--border)', background: 'var(--bg)' }

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '28px 32px', background: 'var(--bg)' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
        <div>
          <div style={{ fontSize: 10, fontFamily: "'JetBrains Mono', monospace", textTransform: 'uppercase' as const, letterSpacing: '0.3em', color: 'var(--text-muted)', marginBottom: 4 }}>// AGENT REVIEW</div>
          <h1 style={{ fontSize: 22, fontWeight: 700, color: 'var(--text-primary)' }}>智能体审核</h1>
        </div>
        <span style={{ padding: '4px 14px', background: agents.length > 0 ? 'var(--action-light)' : 'var(--bg)', color: agents.length > 0 ? 'var(--action)' : 'var(--text-muted)', border: '1px solid ' + (agents.length > 0 ? 'var(--action-border)' : 'var(--border)'), borderRadius: 20, fontSize: 13, fontWeight: 600 }}>
          {agents.length} 个待审核
        </span>
      </div>
      {agents.length === 0 ? (
        <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, padding: '60px 20px', textAlign: 'center' as const }}>
          <div style={{ fontSize: 32, marginBottom: 12 }}>✓</div>
          <div style={{ fontSize: 14, fontWeight: 500, color: 'var(--text-primary)' }}>暂无待审核的智能体</div>
        </div>
      ) : (
        <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, overflow: 'hidden' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead><tr>{['智能体名称','类型','创建者','学科','提交时间','操作'].map(h => <th key={h} style={thStyle}>{h}</th>)}</tr></thead>
            <tbody>
              {agents.map((agent, i) => (
                <tr key={agent.id} style={{ borderBottom: i < agents.length - 1 ? '1px solid var(--border-light)' : 'none' }}>
                  <td style={{ padding: '12px 16px', fontWeight: 500, color: 'var(--text-primary)' }}>{agent.name}</td>
                  <td style={{ padding: '12px 16px' }}>
                    <span style={{ padding: '2px 8px', borderRadius: 4, fontSize: 11, fontWeight: 600, background: agent.type === 'deployed' ? '#F5F3FF' : '#EFF6FF', color: agent.type === 'deployed' ? '#7C3AED' : '#2563EB', border: `1px solid ${agent.type === 'deployed' ? '#DDD6FE' : '#BFDBFE'}` }}>
                      {agent.type === 'deployed' ? '独立部署' : 'Prompt'}
                    </span>
                  </td>
                  <td style={{ padding: '12px 16px', color: 'var(--text-secondary)' }}>{agent.author}</td>
                  <td style={{ padding: '12px 16px', color: 'var(--text-muted)', fontSize: 12 }}>{agent.subject}</td>
                  <td style={{ padding: '12px 16px', color: 'var(--text-muted)', fontSize: 12, fontFamily: "'JetBrains Mono', monospace" }}>{agent.submittedAt}</td>
                  <td style={{ padding: '12px 16px' }}>
                    <div style={{ display: 'flex', gap: 6 }}>
                      <button onClick={() => setDetailId(agent.id)} style={{ padding: '5px 12px', background: 'transparent', color: 'var(--action)', border: '1px solid var(--action-border)', borderRadius: 5, fontSize: 12, cursor: 'pointer', fontFamily: 'inherit' }}>查看详情</button>
                      <button onClick={() => handleApprove(agent.id)} style={{ padding: '5px 12px', background: 'var(--status-done)', color: '#fff', border: 'none', borderRadius: 5, fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>通过</button>
                      <button onClick={() => handleReject(agent.id)} style={{ padding: '5px 12px', background: 'transparent', color: '#DC2626', border: '1px solid #FECACA', borderRadius: 5, fontSize: 12, cursor: 'pointer', fontFamily: 'inherit' }}>拒绝</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {detailAgent && (
        <>
          <div onClick={() => setDetailId(null)} style={{ position: 'fixed', inset: 0, background: 'rgba(13,24,41,0.3)', zIndex: 200 }} />
          <div style={{ position: 'fixed', top: 0, right: 0, bottom: 0, width: 480, background: 'var(--surface)', borderLeft: '1px solid var(--border)', zIndex: 201, display: 'flex', flexDirection: 'column', boxShadow: '-8px 0 24px rgba(11,46,92,0.12)' }}>
            <div style={{ padding: '20px 24px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)' }}>{detailAgent.name}</div>
                <span style={{ padding: '2px 8px', borderRadius: 4, fontSize: 11, fontWeight: 600, background: detailAgent.type === 'deployed' ? '#F5F3FF' : '#EFF6FF', color: detailAgent.type === 'deployed' ? '#7C3AED' : '#2563EB', border: `1px solid ${detailAgent.type === 'deployed' ? '#DDD6FE' : '#BFDBFE'}` }}>
                  {detailAgent.type === 'deployed' ? '独立部署' : 'Prompt'}
                </span>
              </div>
              <button onClick={() => setDetailId(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', fontSize: 20, lineHeight: 1 }}>×</button>
            </div>
            <div style={{ flex: 1, overflowY: 'auto', padding: '20px 24px' }}>
              <InfoRow label="创建者" value={detailAgent.author} />
              <InfoRow label="学科" value={detailAgent.subject} />
              <InfoRow label="所需数据" value={detailAgent.dataNeeded} />
              <div style={{ marginBottom: 16 }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' as const, letterSpacing: '0.1em', marginBottom: 6 }}>功能描述</div>
                <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.7 }}>{detailAgent.desc}</div>
              </div>
              <div style={{ marginBottom: 20 }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' as const, letterSpacing: '0.1em', marginBottom: 8 }}>系统提示词</div>
                <div style={{ background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 6, padding: '12px 14px', fontSize: 12, fontFamily: "'JetBrains Mono', monospace", color: 'var(--text-secondary)', lineHeight: 1.8, whiteSpace: 'pre-wrap' as const }}>{detailAgent.prompt}</div>
              </div>
              <div>
                <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' as const, letterSpacing: '0.1em', marginBottom: 8 }}>拒绝理由（可选）</div>
                <textarea value={rejectReason} onChange={e => setRejectReason(e.target.value)} placeholder="填写拒绝理由，将通知给创建者..." style={{ width: '100%', minHeight: 80, padding: '8px 12px', border: '1px solid var(--border)', borderRadius: 6, fontSize: 12, fontFamily: 'inherit', resize: 'vertical' as const, background: 'var(--surface)', outline: 'none', boxSizing: 'border-box' as const, color: 'var(--text-primary)' }} />
              </div>
            </div>
            <div style={{ padding: '16px 24px', borderTop: '1px solid var(--border)', display: 'flex', gap: 10 }}>
              <button onClick={() => handleApprove(detailAgent.id)} style={{ flex: 1, padding: 9, background: 'var(--status-done)', color: '#fff', border: 'none', borderRadius: 7, fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>✓ 通过</button>
              <button onClick={() => handleReject(detailAgent.id)} style={{ flex: 1, padding: 9, background: '#DC2626', color: '#fff', border: 'none', borderRadius: 7, fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>✗ 拒绝</button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
