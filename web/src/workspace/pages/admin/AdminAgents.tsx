import { useState } from 'react'
import { AdminPageHeader, AdminTableSection } from './AdminUi'
import {
  approveButtonStyle,
  cellStyle,
  emptyStyle,
  monoCellStyle,
  nameCellStyle,
  pageStyle,
  tableStyle,
  tagStyle,
  thStyle,
} from './AdminStyles'

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
    prompt: '你是一位经验丰富的科研项目评审专家。\n\n请对上传的申请书进行以下诊断：\n1. 检查立项依据的论证逻辑：政策背景 → 研究缺口 → 本研究切入点是否成立\n2. 核查研究内容与研究目标的对应关系，是否存在目标虚高或内容不足\n3. 比对研究方案的技术路线是否清晰、创新点是否有文献支撑\n4. 输出差距清单，每条附具体修改建议',
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
  const [rejectError, setRejectError] = useState(false)
  const [showApproveConfirm, setShowApproveConfirm] = useState<string | null>(null)

  const detailAgent = agents.find(a => a.id === detailId)

  const handleApprove = (id: string) => {
    setAgents(prev => prev.filter(a => a.id !== id))
    if (detailId === id) setDetailId(null)
    setShowApproveConfirm(null)
  }

  const handleReject = (id: string) => {
    if (!rejectReason.trim()) {
      setRejectError(true)
      return
    }
    setRejectError(false)
    setAgents(prev => prev.filter(a => a.id !== id))
    if (detailId === id) { setDetailId(null); setRejectReason('') }
  }

  const openDetail = (id: string) => {
    setDetailId(id)
    setRejectReason('')
    setRejectError(false)
  }



  return (
    <div style={pageStyle}>
      <AdminPageHeader eyebrow="// AGENT REVIEW" title="智能体审核" pendingCount={agents.length} />

      <AdminTableSection title="待审核智能体">
        {agents.length === 0 ? (
          <div style={emptyStyle}>暂无待审核的智能体</div>
        ) : (
          <table style={tableStyle}>
            <thead>
              <tr>{['智能体名称', '类型', '创建者', '学科', '提交时间', '操作'].map(label => <th key={label} style={thStyle}>{label}</th>)}</tr>
            </thead>
            <tbody>
              {agents.map((agent, index) => (
                <tr key={agent.id} style={{ borderBottom: index < agents.length - 1 ? '1px solid var(--border-light)' : 'none' }}>
                  <td style={nameCellStyle}>{agent.name}</td>
                  <td style={cellStyle}><span style={tagStyle}>{agent.type === 'deployed' ? '独立部署' : 'Prompt'}</span></td>
                  <td style={cellStyle}>{agent.author}</td>
                  <td style={cellStyle}><span style={tagStyle}>{agent.subject}</span></td>
                  <td style={monoCellStyle}>{agent.submittedAt}</td>
                  <td style={cellStyle}>
                    <button type="button" onClick={() => openDetail(agent.id)} style={approveButtonStyle}>审核</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </AdminTableSection>

      {/* 审核侧抽屉 */}
      {detailAgent && (
        <>
          <div onClick={() => setDetailId(null)} style={{ position: 'fixed', inset: 0, background: 'rgba(13,24,41,0.3)', zIndex: 200 }} />
          <div style={{ position: 'fixed', top: 0, right: 0, bottom: 0, width: 520, background: 'var(--surface)', borderLeft: '1px solid var(--border)', zIndex: 201, display: 'flex', flexDirection: 'column', boxShadow: '-8px 0 24px rgba(11,46,92,0.12)' }}>
            {/* 抽屉头 */}
            <div style={{ padding: '20px 24px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)' }}>{detailAgent.name}</div>
                <span style={{ padding: '2px 8px', borderRadius: 4, fontSize: 11, fontWeight: 600, background: detailAgent.type === 'deployed' ? '#F5F3FF' : '#EFF6FF', color: detailAgent.type === 'deployed' ? '#7C3AED' : '#2563EB', border: `1px solid ${detailAgent.type === 'deployed' ? '#DDD6FE' : '#BFDBFE'}` }}>
                  {detailAgent.type === 'deployed' ? '独立部署' : 'Prompt'}
                </span>
              </div>
              <button onClick={() => setDetailId(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', fontSize: 20, lineHeight: 1 }}>×</button>
            </div>

            {/* 抽屉内容 */}
            <div style={{ flex: 1, overflowY: 'auto', padding: '20px 24px' }}>
              <InfoRow label="创建者" value={detailAgent.author} />
              <InfoRow label="学科" value={detailAgent.subject} />
              <InfoRow label="所需数据" value={detailAgent.dataNeeded} />
              <InfoRow label="提交时间" value={detailAgent.submittedAt} />

              <div style={{ marginBottom: 16 }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' as const, letterSpacing: '0.1em', marginBottom: 6 }}>功能描述</div>
                <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.7 }}>{detailAgent.desc}</div>
              </div>

              <div style={{ marginBottom: 24 }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' as const, letterSpacing: '0.1em', marginBottom: 8 }}>
                  {detailAgent.type === 'deployed' ? '部署需求说明' : '系统提示词'}
                </div>
                <div style={{ background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 6, padding: '12px 14px', fontSize: 12, fontFamily: "'JetBrains Mono', monospace", color: 'var(--text-secondary)', lineHeight: 1.8, whiteSpace: 'pre-wrap' as const }}>
                  {detailAgent.prompt}
                </div>
              </div>

              {/* 拒绝理由输入 */}
              <div>
                <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' as const, letterSpacing: '0.1em', marginBottom: 6 }}>
                  拒绝理由
                  <span style={{ fontWeight: 400, color: '#DC2626', marginLeft: 6, textTransform: 'none', letterSpacing: 0 }}>拒绝时必填</span>
                </div>
                <textarea
                  value={rejectReason}
                  onChange={e => { setRejectReason(e.target.value); setRejectError(false) }}
                  placeholder="填写拒绝理由，将通知给创建者（提示词不够具体、内容不符合平台规范等）..."
                  style={{
                    width: '100%', minHeight: 90, padding: '8px 12px',
                    border: `1px solid ${rejectError ? '#DC2626' : 'var(--border)'}`,
                    borderRadius: 6, fontSize: 12, fontFamily: 'inherit',
                    resize: 'vertical' as const, background: 'var(--surface)',
                    outline: 'none', boxSizing: 'border-box' as const, color: 'var(--text-primary)',
                    transition: 'border-color 0.15s',
                  }}
                />
                {rejectError && (
                  <div style={{ fontSize: 12, color: '#DC2626', marginTop: 4 }}>请填写拒绝理由后再提交</div>
                )}
              </div>
            </div>

            {/* 抽屉底部操作 */}
            <div style={{ padding: '16px 24px', borderTop: '1px solid var(--border)', display: 'flex', gap: 10 }}>
              <button
                onClick={() => setShowApproveConfirm(detailAgent.id)}
                style={{ flex: 1, padding: 11, background: 'var(--status-done)', color: '#fff', border: 'none', borderRadius: 7, fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}
              >✓ 通过</button>
              <button
                onClick={() => handleReject(detailAgent.id)}
                style={{ flex: 1, padding: 11, background: '#DC2626', color: '#fff', border: 'none', borderRadius: 7, fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}
              >✗ 拒绝</button>
            </div>
          </div>
        </>
      )}

      {/* 通过确认弹窗 */}
      {showApproveConfirm && (
        <>
          <div onClick={() => setShowApproveConfirm(null)} style={{ position: 'fixed', inset: 0, background: 'rgba(13,24,41,0.5)', zIndex: 300 }} />
          <div style={{ position: 'fixed', top: '50%', left: '50%', transform: 'translate(-50%,-50%)', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12, padding: 32, width: 400, zIndex: 301, boxShadow: '0 20px 60px rgba(11,46,92,0.2)' }}>
            <div style={{ fontSize: 17, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 10 }}>确认通过审核</div>
            <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.7, marginBottom: 24 }}>
              通过后，该智能体将发布到广场，所有用户均可使用。请确认内容符合平台规范。
            </div>
            <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
              <button onClick={() => setShowApproveConfirm(null)} style={{ padding: '8px 20px', background: 'var(--surface)', color: 'var(--text-secondary)', border: '1px solid var(--border)', borderRadius: 7, fontSize: 13, cursor: 'pointer', fontFamily: 'inherit' }}>取消</button>
              <button onClick={() => handleApprove(showApproveConfirm)} style={{ padding: '8px 20px', background: 'var(--status-done)', color: '#fff', border: 'none', borderRadius: 7, fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>确认通过</button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
