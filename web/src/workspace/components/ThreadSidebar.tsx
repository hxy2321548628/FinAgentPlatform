import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

type RunStatus = 'running' | 'done' | 'failed' | 'waiting'

interface Thread {
  id: string
  title: string
  time: string
  status: RunStatus
}

const MOCK_THREADS: Thread[] = [
  { id: '1', title: '新能源行业波动率分析', time: '进行中', status: 'running' },
  { id: '2', title: 'A 股收益归因分解', time: '昨天 14:32', status: 'done' },
  { id: '3', title: 'Fama-French 三因子复现', time: '2 天前', status: 'done' },
  { id: '4', title: '持仓集中度风险分析', time: '3 天前', status: 'failed' },
  { id: '5', title: '财报核查 · 格力电器', time: '4 天前', status: 'waiting' },
]

const STATUS_ICON: Record<RunStatus, string> = {
  running: '◉',
  done: '✓',
  failed: '✗',
  waiting: '⏸',
}

const STATUS_COLOR: Record<RunStatus, string> = {
  running: 'var(--action)',
  done: 'var(--status-done)',
  failed: '#DC2626',
  waiting: 'var(--status-warn)',
}

export function ThreadSidebar() {
  const navigate = useNavigate()
  const { threadId } = useParams()
  const [hoveredId, setHoveredId] = useState<string | null>(null)
  const [threads, setThreads] = useState(MOCK_THREADS)

  const handleDelete = (e: React.MouseEvent, id: string) => {
    e.stopPropagation()
    setThreads(prev => prev.filter(t => t.id !== id))
    if (threadId === id) navigate('/workspace/chat')
  }

  return (
    <div style={{
      width: 240, flexShrink: 0,
      background: 'var(--surface)',
      borderRight: '1px solid var(--border)',
      display: 'flex', flexDirection: 'column',
      height: '100%', overflow: 'hidden',
    }}>
      <div style={{ padding: '12px 12px 8px' }}>
        <button
          onClick={() => navigate('/workspace/chat')}
          style={{
            width: '100%', padding: '8px 0',
            background: 'var(--action)', color: '#fff',
            border: 'none', borderRadius: 7,
            fontSize: 13, fontWeight: 500,
            cursor: 'pointer', fontFamily: 'inherit',
            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
          }}
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
          </svg>
          新建分析
        </button>
      </div>

      <div style={{ padding: '4px 16px 8px', fontSize: 10, fontFamily: "'JetBrains Mono', monospace", textTransform: 'uppercase' as const, letterSpacing: '0.2em', color: 'var(--text-muted)' }}>
        // HISTORY
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '0 8px 8px' }}>
        {threads.map(thread => {
          const isActive = threadId === thread.id
          const isHovered = hoveredId === thread.id
          return (
            <div
              key={thread.id}
              onClick={() => navigate(`/workspace/chat/${thread.id}`)}
              onMouseEnter={() => setHoveredId(thread.id)}
              onMouseLeave={() => setHoveredId(null)}
              style={{
                padding: '10px 12px',
                borderRadius: 7,
                cursor: 'pointer',
                marginBottom: 2,
                position: 'relative' as const,
                background: isActive ? 'var(--action-light)' : isHovered ? 'var(--bg)' : 'transparent',
                border: isActive ? '1px solid var(--action-border)' : '1px solid transparent',
                transition: 'background 0.15s',
              }}
            >
              <div style={{
                fontSize: 13, fontWeight: 500,
                color: isActive ? 'var(--action)' : 'var(--text-primary)',
                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' as const,
                marginBottom: 4, paddingRight: isHovered ? 20 : 0,
              }}>
                {thread.title}
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11 }}>
                <span style={{ color: 'var(--text-muted)' }}>{thread.time}</span>
                <span style={{ color: STATUS_COLOR[thread.status], fontWeight: 600 }}>
                  {STATUS_ICON[thread.status]}
                </span>
              </div>
              {isHovered && (
                <button
                  onClick={e => handleDelete(e, thread.id)}
                  style={{
                    position: 'absolute' as const, top: '50%', right: 10,
                    transform: 'translateY(-50%)',
                    width: 20, height: 20, borderRadius: 4,
                    border: 'none', background: 'transparent',
                    color: 'var(--text-muted)', cursor: 'pointer',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: 12,
                  }}
                  title="删除会话"
                >
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/>
                    <path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4h6v2"/>
                  </svg>
                </button>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
