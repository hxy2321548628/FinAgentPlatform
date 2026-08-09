import { useState, useEffect } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'

// 状态：已创建（含部署中过渡）→ 待审核（申请发布广场）→ 已发布
// deploying 不再作为独立状态，用 isDeploying 标记区分
type AgentStatus = 'created' | 'reviewing' | 'published'
type AgentType = 'prompt' | 'deployed'

interface MyAgent {
  id: string
  name: string
  subject: string
  type: AgentType
  status: AgentStatus
  isDeploying?: boolean
  applyingScenario?: boolean
  rejectedReason?: string     // 有值表示被拒绝，内容为拒绝理由
  calls?: number
  rating?: number
  publishedAt?: string
  submittedAt?: string
}

const STATUS_LABEL: Record<AgentStatus, string> = {
  created:   '已创建',
  reviewing: '待审核',
  published: '已发布',
}
const STATUS_STYLE: Record<AgentStatus, { bg: string; color: string }> = {
  created:   { bg: '#EFF6FF', color: '#2563EB' },
  reviewing: { bg: '#FFFBEB', color: 'var(--status-warn)' },
  published: { bg: '#ECFDF5', color: 'var(--status-done)' },
}

const MOCK_MY_AGENTS: MyAgent[] = [
  // 已发布（申请了场景库）
  { id: '1', name: '企业财务异常检测',  subject: '金融学', type: 'prompt',   status: 'published', calls: 96,  rating: 4.8, publishedAt: '2026-07-20', applyingScenario: true },
  // 已发布（正常）
  { id: '2', name: '计量方法鉴别器',    subject: '经济学', type: 'prompt',   status: 'published', calls: 41,  rating: 4.5, publishedAt: '2026-08-01' },
  // 待审核（正常等待中）
  { id: '3', name: '创新点对比分析',    subject: '金融学', type: 'prompt',   status: 'reviewing', submittedAt: '2026-08-09 14:22' },
  // 待审核（独立部署）
  { id: '4', name: '财报实时爬取 Agent', subject: '会计学', type: 'deployed', status: 'reviewing', submittedAt: '2026-08-09 16:05' },
  // 待审核（审核被拒绝，显示拒绝理由，可修改后重新提交）
  { id: '8', name: '宏观政策解读助手', subject: '经济学', type: 'prompt',   status: 'reviewing', submittedAt: '2026-08-07 10:30', rejectedReason: '系统提示词过于宽泛，未明确分析步骤与输出格式，建议细化分析逻辑后重新提交。' },
  // 已创建（普通 Prompt）
  { id: '5', name: '股价动量因子筛选',  subject: '金融学', type: 'prompt',   status: 'created' },
  // 已创建（独立部署，部署中）
  { id: '6', name: '财报 OCR 解析',    subject: '会计学', type: 'deployed', status: 'created', isDeploying: true },
  // 已创建（独立部署，已完成）
  { id: '7', name: '舆情监控 Agent',   subject: '金融学', type: 'deployed', status: 'created', isDeploying: false },
]

const TABS: AgentStatus[] = ['created', 'reviewing', 'published']

export function MyAgents() {
  const navigate = useNavigate()
  const location = useLocation()
  const [activeTab, setActiveTab] = useState<AgentStatus>('created')
  const [agents, setAgents] = useState(MOCK_MY_AGENTS)
  const [showScenarioModal, setShowScenarioModal] = useState(false)
  const [selectedAgentForScenario, setSelectedAgentForScenario] = useState('')
  const [toast, setToast] = useState<string | null>((location.state as { toast?: string })?.toast ?? null)

  // toast 3 秒后自动消失
  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(null), 3000)
    return () => clearTimeout(t)
  }, [toast])

  const filtered = agents.filter(a => a.status === activeTab)

  // 已发布且未申请场景库的 agent，供申请弹窗选择
  const publishedAgents = agents.filter(a => a.status === 'published' && !a.applyingScenario)

  const handleOffline = (id: string) =>
    setAgents(prev => prev.map(a => a.id === id ? { ...a, status: 'created' as AgentStatus } : a))

  const handleApplyScenario = () => {
    if (!selectedAgentForScenario) return
    setAgents(prev => prev.map(a =>
      a.id === selectedAgentForScenario ? { ...a, applyingScenario: true } : a
    ))
    setShowScenarioModal(false)
    setSelectedAgentForScenario('')
  }

  const emptyText: Record<AgentStatus, string> = {
    created:   '还没有已创建的智能体',
    reviewing: '没有待审核的智能体',
    published: '还没有发布到广场的智能体',
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '32px 36px', background: 'var(--bg)' }}>
      {/* 页头 */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 28 }}>
        <div>
          <div style={{ fontSize: 10, fontFamily: "'JetBrains Mono', monospace", textTransform: 'uppercase' as const, letterSpacing: '0.3em', color: 'var(--text-muted)', marginBottom: 6 }}>// MY AGENTS</div>
          <h1 style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>我的智能体</h1>
          <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>管理你创建的分析智能体，发布到广场或申请上架场景库</p>
        </div>
        <div style={{ display: 'flex', gap: 10, flexShrink: 0 }}>
          <button
            onClick={() => setShowScenarioModal(true)}
            disabled={publishedAgents.length === 0}
            style={{ padding: '9px 16px', background: 'transparent', color: publishedAgents.length > 0 ? 'var(--action)' : 'var(--text-muted)', border: '1px solid ' + (publishedAgents.length > 0 ? 'var(--action-border)' : 'var(--border)'), borderRadius: 7, fontSize: 13, fontWeight: 500, cursor: publishedAgents.length > 0 ? 'pointer' : 'default', fontFamily: 'inherit' }}
          >
            申请上架场景库
          </button>
          <button
            onClick={() => navigate('/workspace/my-agents/create')}
            style={{ padding: '9px 20px', background: 'var(--action)', color: '#fff', border: 'none', borderRadius: 7, fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}
          >
            + 创建智能体
          </button>
        </div>
      </div>

      {/* Toast 提示 */}
      {toast && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 10,
          background: '#ECFDF5', border: '1px solid #A7F3D0',
          borderRadius: 8, padding: '10px 16px', marginBottom: 20,
          fontSize: 13, color: '#065F46',
          animation: 'card-enter 0.3s ease-out',
        }}>
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><polyline points="20 6 9 17 4 12"/></svg>
          {toast}
        </div>
      )}

      {/* Tab */}
      <div style={{ display: 'flex', borderBottom: '1px solid var(--border)', marginBottom: 20 }}>
        {TABS.map(tab => (
          <button key={tab} onClick={() => setActiveTab(tab)} style={{
            padding: '10px 20px', fontSize: 13, fontWeight: 500,
            background: 'none', border: 'none',
            borderBottom: activeTab === tab ? '2px solid var(--action)' : '2px solid transparent',
            marginBottom: -1, cursor: 'pointer', fontFamily: 'inherit',
            color: activeTab === tab ? 'var(--action)' : 'var(--text-muted)',
            transition: 'color 0.15s',
          }}>
            {STATUS_LABEL[tab]}
            <span style={{ marginLeft: 6, fontSize: 11, background: 'var(--bg)', padding: '1px 6px', borderRadius: 10, color: 'var(--text-muted)' }}>
              {agents.filter(a => a.status === tab).length}
            </span>
          </button>
        ))}
      </div>

      {/* 列表 */}
      {filtered.length === 0 ? (
        <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, padding: '48px 20px', textAlign: 'center' as const }}>
          <div style={{ marginBottom: 12, color: 'var(--action)' }}>
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
          </div>
          <div style={{ fontSize: 14, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 6 }}>{emptyText[activeTab]}</div>
          {activeTab !== 'reviewing' && (            <button onClick={() => navigate('/workspace/my-agents/create')} style={{ marginTop: 8, padding: '8px 20px', background: 'var(--action)', color: '#fff', border: 'none', borderRadius: 7, fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>+ 创建智能体</button>
          )}
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column' as const, gap: 10 }}>
          {filtered.map(agent => {
            return (
              <div key={agent.id} style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, padding: '16px 20px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16 }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4, flexWrap: 'wrap' as const }}>
                    <span style={{ fontSize: 15, fontWeight: 600, color: 'var(--text-primary)' }}>{agent.name}</span>
                    {agent.type === 'deployed' && (
                      <span style={{ padding: '1px 7px', borderRadius: 4, fontSize: 10, fontWeight: 700, background: '#F5F3FF', color: '#7C3AED', border: '1px solid #DDD6FE' }}>独立部署</span>
                    )}
                    {agent.isDeploying && (
                      <span style={{ padding: '1px 7px', borderRadius: 4, fontSize: 10, fontWeight: 600, background: '#F5F3FF', color: '#7C3AED', border: '1px solid #DDD6FE', display: 'inline-flex', alignItems: 'center', gap: 3 }}>
                        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                        部署中
                      </span>
                    )}
                    {agent.rejectedReason && (
                      <span style={{ padding: '1px 7px', borderRadius: 4, fontSize: 10, fontWeight: 600, background: '#FEF2F2', color: '#DC2626', border: '1px solid #FECACA' }}>已拒绝</span>
                    )}
                    <span style={{ padding: '2px 8px', borderRadius: 10, fontSize: 11, fontWeight: 600, background: STATUS_STYLE[agent.status].bg, color: STATUS_STYLE[agent.status].color }}>{STATUS_LABEL[agent.status]}</span>
                    {agent.applyingScenario && (
                      <span style={{ padding: '1px 7px', borderRadius: 4, fontSize: 10, fontWeight: 600, background: '#FFFBEB', color: 'var(--status-warn)', border: '1px solid #FDE68A', display: 'inline-flex', alignItems: 'center', gap: 3 }}>
                        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                        申请场景库中
                      </span>
                    )}
                    {agent.calls !== undefined && <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{agent.calls} 次调用</span>}
                    {agent.rating !== undefined && <span style={{ fontSize: 12, color: 'var(--text-muted)', display: 'inline-flex', alignItems: 'center', gap: 3 }}>
                      <svg width="11" height="11" viewBox="0 0 24 24" fill="#F59E0B" stroke="none"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
                      {agent.rating}
                    </span>}
                  </div>
                  {/* 拒绝理由（待审核 Tab 里展示）*/}
                  {agent.rejectedReason && (
                    <div style={{ fontSize: 12, color: '#DC2626', background: '#FEF2F2', border: '1px solid #FECACA', borderRadius: 6, padding: '7px 12px', marginTop: 4 }}>
                      <span style={{ fontWeight: 600 }}>审核未通过：</span>{agent.rejectedReason}
                    </div>
                  )}
                  <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                    {agent.subject}
                    {agent.publishedAt && ` · ${agent.publishedAt} 发布`}
                    {agent.submittedAt && ` · ${agent.submittedAt} 提交审核`}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 8, flexShrink: 0 }}>
                  {agent.status === 'created' && !agent.isDeploying && (
                    <>
                      <button
                        onClick={() => navigate('/workspace/chat', { state: { agentId: agent.id, agentName: agent.name, agentAuthor: agent.subject, agentDataNeeded: '' } })}
                        style={{ padding: '6px 14px', background: 'var(--action)', color: '#fff', border: 'none', borderRadius: 6, fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}
                      >直接对话</button>
                      <button onClick={() => navigate('/workspace/my-agents/create')} style={{ padding: '6px 14px', background: 'transparent', color: 'var(--text-secondary)', border: '1px solid var(--border)', borderRadius: 6, fontSize: 12, cursor: 'pointer', fontFamily: 'inherit' }}>编辑</button>
                      <button onClick={() => navigate('/workspace/agents/publish')} style={{ padding: '6px 14px', background: 'transparent', color: 'var(--action)', border: '1px solid var(--action-border)', borderRadius: 6, fontSize: 12, cursor: 'pointer', fontFamily: 'inherit' }}>发布到广场</button>
                    </>
                  )}
                  {agent.status === 'created' && agent.isDeploying && (
                    <span style={{ fontSize: 12, color: '#7C3AED', padding: '6px 0' }}>等待后台部署完成</span>
                  )}
                  {agent.status === 'published' && (
                    <>
                      <button onClick={() => navigate('/workspace/my-agents/create')} style={{ padding: '6px 14px', background: 'transparent', color: 'var(--text-secondary)', border: '1px solid var(--border)', borderRadius: 6, fontSize: 12, cursor: 'pointer', fontFamily: 'inherit' }}>编辑</button>
                      <button onClick={() => handleOffline(agent.id)} style={{ padding: '6px 14px', background: 'transparent', color: '#DC2626', border: '1px solid #FECACA', borderRadius: 6, fontSize: 12, cursor: 'pointer', fontFamily: 'inherit' }}>下线</button>
                    </>
                  )}
                  {agent.status === 'reviewing' && !agent.rejectedReason && (
                    <span style={{ fontSize: 12, color: 'var(--text-muted)', padding: '6px 0' }}>等待审核</span>
                  )}
                  {agent.status === 'reviewing' && agent.rejectedReason && (
                    <button onClick={() => navigate('/workspace/my-agents/create')} style={{ padding: '6px 14px', background: 'var(--action)', color: '#fff', border: 'none', borderRadius: 6, fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>修改后重新提交</button>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* 申请上架场景库弹窗 */}
      {showScenarioModal && (
        <>
          <div onClick={() => setShowScenarioModal(false)} style={{ position: 'fixed', inset: 0, background: 'rgba(13,24,41,0.4)', backdropFilter: 'blur(4px)', zIndex: 200 }} />
          <div style={{ position: 'fixed', top: '50%', left: '50%', transform: 'translate(-50%,-50%)', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12, padding: 32, width: 440, zIndex: 201, boxShadow: '0 20px 60px rgba(11,46,92,0.2)' }}>
            <div style={{ fontSize: 17, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 6 }}>申请上架场景库</div>
            <div style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 24, lineHeight: 1.6 }}>
              选择一个已发布到广场的智能体，提交上架申请后由管理员审核。通过后将出现在场景库供所有用户使用。
            </div>
            <div style={{ marginBottom: 20 }}>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' as const, letterSpacing: '0.1em', marginBottom: 8 }}>选择智能体</label>
              <select
                value={selectedAgentForScenario}
                onChange={e => setSelectedAgentForScenario(e.target.value)}
                style={{ width: '100%', padding: '10px 12px', border: '1px solid var(--border)', borderRadius: 7, fontSize: 13, fontFamily: 'inherit', background: 'var(--surface)', color: selectedAgentForScenario ? 'var(--text-primary)' : 'var(--text-muted)', outline: 'none', cursor: 'pointer' }}
              >
                <option value="">-- 选择已发布的智能体 --</option>
                {publishedAgents.map(a => (
                  <option key={a.id} value={a.id}>{a.name}（{a.subject}）</option>
                ))}
              </select>
            </div>
            <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
              <button onClick={() => { setShowScenarioModal(false); setSelectedAgentForScenario('') }} style={{ padding: '8px 18px', background: 'var(--surface)', color: 'var(--text-secondary)', border: '1px solid var(--border)', borderRadius: 7, fontSize: 13, cursor: 'pointer', fontFamily: 'inherit' }}>取消</button>
              <button
                onClick={handleApplyScenario}
                disabled={!selectedAgentForScenario}
                style={{ padding: '8px 18px', background: selectedAgentForScenario ? 'var(--action)' : 'var(--text-muted)', color: '#fff', border: 'none', borderRadius: 7, fontSize: 13, fontWeight: 600, cursor: selectedAgentForScenario ? 'pointer' : 'default', fontFamily: 'inherit' }}
              >提交申请</button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
