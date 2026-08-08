import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

type AgentStatus = 'draft' | 'reviewing' | 'published'

interface MyAgent {
  id: string; name: string; subject: string; status: AgentStatus
  calls?: number; rating?: number; publishedAt?: string; submittedAt?: string
}

const STATUS_LABEL: Record<AgentStatus, string> = { draft: '草稿', reviewing: '审核中', published: '已发布' }
const STATUS_STYLE: Record<AgentStatus, { bg: string; color: string }> = {
  draft:     { bg: 'var(--bg)', color: 'var(--text-muted)' },
  reviewing: { bg: '#FFFBEB', color: 'var(--status-warn)' },
  published: { bg: '#ECFDF5', color: 'var(--status-done)' },
}

const MOCK_MY_AGENTS: MyAgent[] = [
  { id: '1', name: '企业财务异常检测', subject: '金融学', status: 'published', calls: 96, rating: 4.8, publishedAt: '2026-07-20' },
  { id: '2', name: '创新点对比分析', subject: '金融学', status: 'reviewing', submittedAt: '2026-08-07 14:22' },
  { id: '3', name: '股价动量因子筛选', subject: '金融学', status: 'draft' },
]

const TABS: AgentStatus[] = ['draft', 'reviewing', 'published']

export function MyAgents() {
  const navigate = useNavigate()
  const [activeTab, setActiveTab] = useState<AgentStatus>('published')
  const [agents, setAgents] = useState(MOCK_MY_AGENTS)
  const filtered = agents.filter(a => a.status === activeTab)

  const handleOffline = (id: string) => setAgents(prev => prev.map(a => a.id === id ? { ...a, status: 'draft' as AgentStatus } : a))

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '32px 36px', background: 'var(--bg)' }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 28 }}>
        <div>
          <div style={{ fontSize: 10, fontFamily: "'JetBrains Mono', monospace", textTransform: 'uppercase' as const, letterSpacing: '0.3em', color: 'var(--text-muted)', marginBottom: 6 }}>// MY AGENTS</div>
          <h1 style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>我的智能体</h1>
          <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>管理你创建和发布的分析智能体</p>
        </div>
        <button onClick={() => navigate('/workspace/agents/new')} style={{ padding: '9px 20px', background: 'var(--action)', color: '#fff', border: 'none', borderRadius: 7, fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>+ 创建智能体</button>
      </div>

      {/* Tab */}
      <div style={{ display: 'flex', borderBottom: '1px solid var(--border)', marginBottom: 20 }}>
        {TABS.map(tab => (
          <button key={tab} onClick={() => setActiveTab(tab)} style={{ padding: '10px 20px', fontSize: 13, fontWeight: 500, background: 'none', border: 'none', borderBottom: activeTab === tab ? '2px solid var(--action)' : '2px solid transparent', marginBottom: -1, cursor: 'pointer', fontFamily: 'inherit', color: activeTab === tab ? 'var(--action)' : 'var(--text-muted)', transition: 'color 0.15s' }}>
            {STATUS_LABEL[tab]}
            <span style={{ marginLeft: 6, fontSize: 11, background: 'var(--bg)', padding: '1px 6px', borderRadius: 10, color: 'var(--text-muted)' }}>{agents.filter(a => a.status === tab).length}</span>
          </button>
        ))}
      </div>

      {filtered.length === 0 ? (
        <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, padding: '48px 20px', textAlign: 'center' as const }}>
          <div style={{ fontSize: 32, marginBottom: 12 }}>✨</div>
          <div style={{ fontSize: 14, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 6 }}>
            {activeTab === 'draft' ? '没有草稿' : activeTab === 'reviewing' ? '没有待审核的智能体' : '还没有发布的智能体'}
          </div>
          {activeTab !== 'reviewing' && (
            <button onClick={() => navigate('/workspace/agents/new')} style={{ marginTop: 8, padding: '8px 20px', background: 'var(--action)', color: '#fff', border: 'none', borderRadius: 7, fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>+ 创建智能体</button>
          )}
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column' as const, gap: 10 }}>
          {filtered.map(agent => {
            const ss = STATUS_STYLE[agent.status]
            return (
              <div key={agent.id} style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, padding: '16px 20px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16 }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
                    <span style={{ fontSize: 15, fontWeight: 600, color: 'var(--text-primary)' }}>{agent.name}</span>
                    <span style={{ padding: '2px 8px', borderRadius: 10, fontSize: 11, fontWeight: 600, background: ss.bg, color: ss.color }}>{STATUS_LABEL[agent.status]}</span>
                    {agent.calls !== undefined && <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{agent.calls} 次调用</span>}
                    {agent.rating !== undefined && <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>⭐ {agent.rating}</span>}
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                    {agent.subject}
                    {agent.publishedAt && ` · ${agent.publishedAt} 发布`}
                    {agent.submittedAt && ` · ${agent.submittedAt} 提交`}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 8, flexShrink: 0 }}>
                  {agent.status === 'draft' && <button onClick={() => navigate('/workspace/agents/new')} style={{ padding: '6px 14px', background: 'var(--action)', color: '#fff', border: 'none', borderRadius: 6, fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>编辑</button>}
                  {agent.status === 'published' && (
                    <>
                      <button onClick={() => navigate('/workspace/agents/new')} style={{ padding: '6px 14px', background: 'transparent', color: 'var(--text-secondary)', border: '1px solid var(--border)', borderRadius: 6, fontSize: 12, cursor: 'pointer', fontFamily: 'inherit' }}>编辑</button>
                      <button onClick={() => handleOffline(agent.id)} style={{ padding: '6px 14px', background: 'transparent', color: '#DC2626', border: '1px solid #FECACA', borderRadius: 6, fontSize: 12, cursor: 'pointer', fontFamily: 'inherit' }}>下线</button>
                    </>
                  )}
                  {agent.status === 'reviewing' && <span style={{ fontSize: 12, color: 'var(--text-muted)', padding: '6px 0' }}>等待审核</span>}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
