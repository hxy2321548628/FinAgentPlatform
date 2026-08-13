import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { WorkspaceFiles } from '../components/WorkspaceFiles'

interface ThreadSummary {
  id: string
  title: string
  updated_at: string
}

const FALLBACK_THREADS: ThreadSummary[] = [
  { id: '1', title: '新能源行业波动率分析', updated_at: '2026-08-12T06:14:00Z' },
  { id: '2', title: 'A 股收益归因分解', updated_at: '2026-08-11T06:32:00Z' },
  { id: '3', title: 'Fama-French 三因子复现', updated_at: '2026-08-10T09:15:00Z' },
]

export function MyData() {
  const navigate = useNavigate()
  const [threads, setThreads] = useState<ThreadSummary[]>(FALLBACK_THREADS)
  const [selectedId, setSelectedId] = useState(FALLBACK_THREADS[0].id)

  useEffect(() => {
    const load = async () => {
      try {
        const response = await fetch('/api/threads?limit=100', { credentials: 'include' })
        if (!response.ok) return
        const body = await response.json() as { items: ThreadSummary[] }
        if (body.items.length === 0) return
        setThreads(body.items)
        setSelectedId(current => body.items.some(thread => thread.id === current) ? current : body.items[0].id)
      } catch {
        // API 未启动时保留原型数据，页面仍可完成交互评审。
      }
    }
    void load()
  }, [])

  const selected = threads.find(thread => thread.id === selectedId) ?? threads[0]

  return (
    <div style={{ flex: 1, minHeight: 0, overflow: 'hidden', padding: '28px 32px', background: 'var(--bg)', display: 'flex', flexDirection: 'column' }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 20, flexShrink: 0 }}>
        <div>
          <div style={{ fontSize: 10, fontFamily: "'JetBrains Mono', monospace", textTransform: 'uppercase', letterSpacing: '0.3em', color: 'var(--text-muted)', marginBottom: 6 }}>// THREAD WORKSPACES</div>
          <h1 style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>工作空间</h1>
          <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>每个分析对话拥有独立目录；选择 thread 后管理其中的文件。</p>
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          {selected && <button type="button" onClick={() => navigate(`/workspace/chat/${encodeURIComponent(selected.id)}`)} style={{ padding: '9px 18px', border: '1px solid var(--border)', borderRadius: 7, background: 'var(--surface)', color: 'var(--text-secondary)', fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>进入对话 →</button>}
          <button type="button" onClick={() => navigate('/workspace/chat')} style={{ padding: '9px 18px', border: 'none', borderRadius: 7, background: 'var(--action)', color: '#fff', fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>＋ 新建分析</button>
        </div>
      </div>

      <div style={{ flex: 1, minHeight: 0, display: 'grid', gridTemplateColumns: '320px minmax(0, 1fr)', gap: 16 }}>
        <aside style={{ minHeight: 0, overflowY: 'auto', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10 }}>
          <div style={{ padding: '11px 16px', borderBottom: '1px solid var(--border)', fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', letterSpacing: '0.12em' }}>THREAD 列表</div>
          {threads.map(thread => {
            const active = thread.id === selected?.id
            return (
              <button key={thread.id} type="button" onClick={() => setSelectedId(thread.id)} style={{ width: '100%', padding: '14px 16px', border: 'none', borderBottom: '1px solid var(--border-light)', borderLeft: active ? '3px solid var(--action)' : '3px solid transparent', background: active ? 'var(--action-light)' : 'transparent', textAlign: 'left', cursor: 'pointer', fontFamily: 'inherit' }}>
                <span style={{ display: 'block', fontSize: 13, fontWeight: 600, color: active ? 'var(--action)' : 'var(--text-primary)', marginBottom: 5, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{thread.title || '新对话'}</span>
                <span style={{ display: 'block', fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>{new Date(thread.updated_at).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })}</span>
              </button>
            )
          })}
        </aside>

        <section style={{ minWidth: 0, minHeight: 0, overflow: 'hidden', border: '1px solid var(--border)', borderRadius: 10 }}>
          {selected ? <WorkspaceFiles threadId={selected.id} title={selected.title || '新对话'} /> : <div style={{ padding: 40, color: 'var(--text-muted)' }}>暂无工作空间</div>}
        </section>
      </div>
    </div>
  )
}
