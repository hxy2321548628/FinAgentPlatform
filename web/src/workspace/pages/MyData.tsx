import { useInfiniteQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { errorMessage } from '../../api/request'
import { listThreads, threadKeys } from '../../api/threads'
import { WorkspaceFiles } from '../components/WorkspaceFiles'
import { ExternalLink, MessageSquarePlus } from 'lucide-react'

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
    <div className="workspace-data-page">
      <header className="workspace-data-header">
        <div>
          <div className="page-eyebrow">// THREAD WORKSPACES</div>
          <h1 className="page-title">工作空间</h1>
          <p className="page-desc">选择一个分析会话，在文件树中管理它的独立工作目录。</p>
        </div>
        <div className="workspace-data-actions">
          <label className="workspace-thread-picker">
            <span>当前会话</span>
            <select
              aria-label="选择工作空间会话"
              value={selected?.id ?? ''}
              onChange={event => setSelectedId(event.target.value)}
              disabled={threads.length === 0}
            >
              {threads.length === 0 && <option value="">暂无会话</option>}
              {threads.map(thread => <option key={thread.id} value={thread.id}>{thread.title || '新对话'}</option>)}
            </select>
          </label>
          {threadsQuery.hasNextPage && <button type="button" className="workspace-data-secondary" disabled={threadsQuery.isFetchingNextPage} onClick={() => void threadsQuery.fetchNextPage()}>
            {threadsQuery.isFetchingNextPage ? '加载中…' : '加载更早会话'}
          </button>}
          {selected && <button type="button" className="workspace-data-icon" onClick={() => navigate(`/workspace/chat/${encodeURIComponent(selected.id)}`)} aria-label="进入当前对话" title="进入当前对话"><ExternalLink size={16} /></button>}
          <button type="button" className="workspace-data-primary" onClick={() => navigate('/workspace/chat')}><MessageSquarePlus size={15} />新建分析</button>
        </div>
      </header>

      <main className="workspace-data-content">
        {threadsQuery.isPending && <div className="workspace-data-state">正在加载工作空间…</div>}
        {threadsQuery.isError && <div role="alert" className="workspace-data-state error">{errorMessage(threadsQuery.error)}</div>}
        {!threadsQuery.isPending && !threadsQuery.isError && selected && <WorkspaceFiles threadId={selected.id} title={selected.title || '新对话'} />}
        {!threadsQuery.isPending && !threadsQuery.isError && !selected && (
          <div className="workspace-data-empty">
            <MessageSquarePlus size={30} strokeWidth={1.3} />
            <strong>还没有可管理的工作空间</strong>
            <span>发起一次分析后，对话产生的脚本、数据和图表会出现在这里。</span>
            <button type="button" className="workspace-data-primary" onClick={() => navigate('/workspace/chat')}>新建分析</button>
          </div>
        )}
      </main>
    </div>
  )
}
