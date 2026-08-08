import { useNavigate } from 'react-router-dom'

const MOCK_STATE = {
  hasRunningRun: true,
  runningTitle: '新能源行业波动率分析',
  runningElapsed: '2m14s',
  tokenUsed: 97200,
  tokenQuota: 120000,
  monthlyRuns: 12,
  outputFiles: 34,
  agentCalls: 9,
}

const MOCK_SESSIONS = [
  { id: '1', title: '新能源行业波动率分析', time: '进行中', status: 'running' as const, tokens: 12430 },
  { id: '2', title: 'A 股收益归因分解', time: '昨天 14:32', status: 'done' as const, tokens: 31340 },
  { id: '3', title: '基金最大回撤计算', time: '2 天前', status: 'done' as const, tokens: 8920 },
  { id: '4', title: 'Fama-French 三因子复现', time: '3 天前', status: 'done' as const, tokens: 45230 },
  { id: '5', title: '持仓集中度风险分析', time: '4 天前', status: 'failed' as const, tokens: 3210 },
]

const STATUS_COLOR = {
  running: 'var(--action)',
  done: 'var(--status-done)',
  failed: '#DC2626',
} as const

const STATUS_LABEL = {
  running: '◉ 运行中',
  done: '✓ 完成',
  failed: '✗ 失败',
} as const

function StatCard({ label, value, unit, pct }: { label: string; value: string; unit: string; pct?: number }) {
  return (
    <div style={{
      background: 'var(--surface)', border: '1px solid var(--border)',
      borderRadius: 10, padding: '18px 20px',
    }}>
      <div style={{ fontSize: 11, textTransform: 'uppercase' as const, letterSpacing: '0.12em', color: 'var(--text-muted)', fontFamily: "'JetBrains Mono', monospace", marginBottom: 8 }}>{label}</div>
      <div style={{ fontSize: 26, fontWeight: 800, color: 'var(--text-primary)', fontFamily: "'JetBrains Mono', monospace", lineHeight: 1, marginBottom: 4 }}>{value}</div>
      <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{unit}</div>
      {pct !== undefined && (
        <div style={{ marginTop: 10, height: 4, background: 'var(--border-light)', borderRadius: 2, overflow: 'hidden' }}>
          <div style={{ height: '100%', width: `${pct}%`, background: pct > 80 ? 'var(--status-warn)' : 'var(--action)', borderRadius: 2, transition: 'width 0.4s' }} />
        </div>
      )}
    </div>
  )
}

function ActionBanner() {
  const navigate = useNavigate()
  const { hasRunningRun, runningTitle, runningElapsed, tokenUsed, tokenQuota } = MOCK_STATE
  const pct = Math.round(tokenUsed / tokenQuota * 100)

  if (hasRunningRun) {
    return (
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        background: 'var(--action-light)', border: '1px solid var(--action-border)',
        borderLeft: '4px solid var(--action)',
        borderRadius: 8, padding: '14px 20px', marginBottom: 20,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ color: 'var(--action)', fontSize: 14, fontWeight: 600 }}>◉</span>
          <div>
            <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>分析进行中</span>
            <span style={{ fontSize: 13, color: 'var(--text-secondary)', marginLeft: 10 }}>{runningTitle} · 已用时 {runningElapsed}</span>
          </div>
        </div>
        <button
          onClick={() => navigate('/workspace/chat/1')}
          style={{ padding: '7px 16px', background: 'var(--action)', color: '#fff', border: 'none', borderRadius: 6, fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}
        >
          查看进度 →
        </button>
      </div>
    )
  }

  if (pct > 80) {
    return (
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        background: '#FFFBEB', border: '1px solid #FDE68A',
        borderLeft: '4px solid var(--status-warn)',
        borderRadius: 8, padding: '14px 20px', marginBottom: 20,
      }}>
        <span style={{ fontSize: 14, color: '#92400E' }}>⚠️ 本月 token 已用 {pct}%，剩余 {((tokenQuota - tokenUsed) / 1000).toFixed(0)}K</span>
        <button
          onClick={() => navigate('/settings')}
          style={{ padding: '7px 16px', background: 'transparent', color: '#92400E', border: '1px solid #FDE68A', borderRadius: 6, fontSize: 13, cursor: 'pointer', fontFamily: 'inherit' }}
        >
          查看用量 →
        </button>
      </div>
    )
  }

  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      background: 'var(--bg)', border: '1px solid var(--border)',
      borderLeft: '4px solid var(--border)',
      borderRadius: 8, padding: '14px 20px', marginBottom: 20,
    }}>
      <span style={{ fontSize: 14, color: 'var(--text-secondary)' }}>从场景库开始你的下一次分析</span>
      <button
        onClick={() => navigate('/workspace/scenarios')}
        style={{ padding: '7px 16px', background: 'var(--action)', color: '#fff', border: 'none', borderRadius: 6, fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}
      >
        浏览场景库 →
      </button>
    </div>
  )
}

export function Overview() {
  const navigate = useNavigate()
  const { tokenUsed, tokenQuota, monthlyRuns, outputFiles, agentCalls } = MOCK_STATE
  const tokenPct = Math.round(tokenUsed / tokenQuota * 100)

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '32px 36px', background: 'var(--bg)' }}>
      {/* 页头 */}
      <div style={{ marginBottom: 24 }}>
        <div style={{ fontSize: 10, fontFamily: "'JetBrains Mono', monospace", textTransform: 'uppercase' as const, letterSpacing: '0.3em', color: 'var(--text-muted)', marginBottom: 6 }}>
          // OVERVIEW
        </div>
        <h1 style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)' }}>总览</h1>
        <p style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 4 }}>
          {new Date().toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric', weekday: 'long' })}
        </p>
      </div>

      {/* 行动建议 */}
      <ActionBanner />

      {/* 统计卡片 */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14, marginBottom: 28 }}>
        <StatCard label="本月分析" value={String(monthlyRuns)} unit="次 run" />
        <StatCard label="Token 消耗" value={`${(tokenUsed / 1000).toFixed(0)}K`} unit={`/ ${tokenQuota / 1000}K tokens`} pct={tokenPct} />
        <StatCard label="产出文件" value={String(outputFiles)} unit="个文件" />
        <StatCard label="Agent 调用" value={String(agentCalls)} unit="次（我发布的）" />
      </div>

      {/* 下半部分：最近会话 + 快速入口 */}
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 20 }}>

        {/* 最近会话 */}
        <div>
          <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 12 }}>最近会话</div>
          <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, overflow: 'hidden' }}>
            {MOCK_SESSIONS.map((session, i) => (
              <div
                key={session.id}
                onClick={() => navigate(`/workspace/chat/${session.id}`)}
                style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  padding: '12px 16px',
                  borderBottom: i < MOCK_SESSIONS.length - 1 ? '1px solid var(--border-light)' : 'none',
                  cursor: 'pointer', transition: 'background 0.15s',
                }}
                onMouseEnter={e => (e.currentTarget as HTMLElement).style.background = 'var(--bg)'}
                onMouseLeave={e => (e.currentTarget as HTMLElement).style.background = 'transparent'}
              >
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', marginBottom: 3 }}>
                    {session.title}
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: "'JetBrains Mono', monospace" }}>
                    {session.time} · {(session.tokens / 1000).toFixed(1)}K tokens
                  </div>
                </div>
                <span style={{ fontSize: 11, fontWeight: 600, color: STATUS_COLOR[session.status], marginLeft: 16, flexShrink: 0 }}>
                  {STATUS_LABEL[session.status]}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* 快速入口 */}
        <div>
          <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 12 }}>快速入口</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {[
              { label: '新建分析对话', desc: '直接描述需求，智能体开始工作', to: '/workspace/chat', icon: '💬' },
              { label: '浏览场景库', desc: '从预设分析场景快速启动', to: '/workspace/scenarios', icon: '🗂' },
              { label: '上传数据文件', desc: 'CSV、Excel、PDF 上传至工作区', to: '/workspace/data', icon: '📁' },
            ].map(item => (
              <div
                key={item.to}
                onClick={() => navigate(item.to)}
                style={{
                  background: 'var(--surface)', border: '1px solid var(--border)',
                  borderRadius: 8, padding: '14px 16px', cursor: 'pointer',
                  transition: 'border-color 0.2s, box-shadow 0.2s',
                }}
                onMouseEnter={e => { (e.currentTarget as HTMLElement).style.borderColor = 'var(--action-border)'; (e.currentTarget as HTMLElement).style.boxShadow = '0 2px 8px rgba(23,73,196,0.08)' }}
                onMouseLeave={e => { (e.currentTarget as HTMLElement).style.borderColor = 'var(--border)'; (e.currentTarget as HTMLElement).style.boxShadow = 'none' }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                  <span style={{ fontSize: 16 }}>{item.icon}</span>
                  <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>{item.label}</span>
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-muted)', paddingLeft: 24 }}>{item.desc}</div>
              </div>
            ))}
          </div>
        </div>

      </div>
    </div>
  )
}
