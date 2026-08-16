import { useInfiniteQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { errorMessage } from '../../api/request'
import { listThreads, threadKeys } from '../../api/threads'
import { WorkspaceFiles } from '../components/WorkspaceFiles'

export function MyData() {
  const navigate = useNavigate()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const threadsQuery = useInfiniteQuery({
    queryKey: threadKeys.list(),
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) => listThreads(pageParam),
    getNextPageParam: page => page.next_cursor ?? undefined,
  })
  const threads = threadsQuery.data?.pages.flatMap(page => page.items) ?? []

  const selected = threads.find(thread => thread.id === selectedId) ?? threads[0]

  return (
    <div style={{ flex: 1, minHeight: 0, overflow: 'hidden', padding: '28px 32px', background: 'var(--bg)', display: 'flex', flexDirection: 'column' }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 20, flexShrink: 0 }}>
        <div>
          <div className="page-eyebrow">// THREAD WORKSPACES</div>
          <h1 className="page-title">工作空间</h1>
          <p className="page-desc">每个分析对话拥有独立目录；选择 thread 后管理其中的文件。</p>
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          {selected && <button type="button" onClick={() => navigate(`/workspace/chat/${encodeURIComponent(selected.id)}`)} style={{ padding: '9px 18px', border: '1px solid var(--border)', borderRadius: 7, background: 'var(--surface)', color: 'var(--text-secondary)', fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>进入对话 →</button>}
          <button type="button" onClick={() => navigate('/workspace/chat')} style={{ padding: '9px 18px', border: 'none', borderRadius: 7, background: 'var(--action)', color: '#fff', fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>＋ 新建分析</button>
        </div>
      </div>

      <div style={{ flex: 1, minHeight: 0, display: 'grid', gridTemplateColumns: '320px minmax(0, 1fr)', gap: 16 }}>
        <aside style={{ minHeight: 0, overflowY: 'auto', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10 }}>
          <div style={{ padding: '11px 16px', borderBottom: '1px solid var(--border)', fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', letterSpacing: '0.12em' }}>THREAD 列表</div>
          {threadsQuery.isPending && <div style={{ padding: 16, color: 'var(--text-muted)', fontSize: 12 }}>正在加载会话…</div>}
          {threadsQuery.isError && <div role="alert" style={{ padding: 16, color: 'var(--danger)', fontSize: 12 }}>{errorMessage(threadsQuery.error)}</div>}
          {!threadsQuery.isPending && !threadsQuery.isError && threads.length === 0 && <div style={{ padding: 16, color: 'var(--text-muted)', fontSize: 12 }}>还没有可管理的工作空间</div>}
          {threads.map(thread => {
            const active = thread.id === selected?.id
            return (
              <button key={thread.id} type="button" onClick={() => setSelectedId(thread.id)} style={{ width: '100%', padding: '14px 16px', border: 'none', borderBottom: '1px solid var(--border-light)', borderLeft: active ? '3px solid var(--action)' : '3px solid transparent', background: active ? 'var(--action-light)' : 'transparent', textAlign: 'left', cursor: 'pointer', fontFamily: 'inherit' }}>
                <span style={{ display: 'block', fontSize: 13, fontWeight: 600, color: active ? 'var(--action)' : 'var(--text-primary)', marginBottom: 5, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{thread.title || '新对话'}</span>
                <span style={{ display: 'block', fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>{new Date(thread.updated_at).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })}</span>
              </button>
            )
          })}
          {threadsQuery.hasNextPage && <button type="button" disabled={threadsQuery.isFetchingNextPage} onClick={() => void threadsQuery.fetchNextPage()} style={{ width: '100%', padding: 10, border: 'none', background: 'transparent', color: 'var(--action)', cursor: 'pointer', fontSize: 12 }}>
            {threadsQuery.isFetchingNextPage ? '正在加载…' : '加载更早会话'}
          </button>}
        </aside>

        <section style={{ minWidth: 0, minHeight: 0, overflow: 'hidden', border: '1px solid var(--border)', borderRadius: 10 }}>
          {selected ? <WorkspaceFiles threadId={selected.id} title={selected.title || '新对话'} /> : <div style={{ padding: 40, color: 'var(--text-muted)' }}>暂无工作空间</div>}
        </section>
      </div>
    </div>
  )
}
