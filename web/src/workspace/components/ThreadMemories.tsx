import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Brain, ChevronLeft, RefreshCw, Trash2 } from 'lucide-react'
import { deleteMemory, getMemory, listMemories, memoryKeys } from '../../api/memories'
import { errorMessage } from '../../api/request'
import type { MemoryListResponse, MemorySummary, MemoryType } from '../../api/types'
import { useToast } from '../../components/ui/toast-context'
import { ConfirmDialog } from './ConfirmDialog'

const TYPE_LABEL: Record<MemoryType, string> = {
  user: '用户偏好',
  feedback: '反馈约定',
  project: '项目信息',
  reference: '参考资料',
}

function updatedLabel(value: string): string {
  return new Date(value).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function ThreadMemories({ threadId }: { threadId: string }) {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const [selectedSlug, setSelectedSlug] = useState<string | null>(null)
  const [pendingDelete, setPendingDelete] = useState<{ slug: string; name: string } | null>(null)
  const memories = useQuery({
    queryKey: memoryKeys.list(threadId),
    queryFn: () => listMemories(threadId),
  })
  const detail = useQuery({
    queryKey: memoryKeys.detail(threadId, selectedSlug ?? ''),
    queryFn: () => getMemory(threadId, selectedSlug ?? ''),
    enabled: selectedSlug !== null,
  })
  const remove = useMutation({
    mutationFn: (slug: string) => deleteMemory(threadId, slug),
    async onSuccess(_, slug) {
      queryClient.setQueryData<MemoryListResponse>(memoryKeys.list(threadId), current => (
        current ? { ...current, items: current.items.filter(one => one.slug !== slug) } : current
      ))
      queryClient.removeQueries({ queryKey: memoryKeys.detail(threadId, slug) })
      if (selectedSlug === slug) setSelectedSlug(null)
      await queryClient.invalidateQueries({ queryKey: memoryKeys.list(threadId) })
      toast({ title: '记忆已删除', variant: 'success' })
    },
    onError(error) {
      toast({ title: '记忆删除失败', description: errorMessage(error), variant: 'error' })
    },
  })

  useEffect(() => {
    setSelectedSlug(null)
    setPendingDelete(null)
  }, [threadId])

  const items = memories.data?.items ?? []
  const selected = detail.data ?? items.find(one => one.slug === selectedSlug)

  return (
    <section className="thread-memories" aria-label="会话记忆">
      <header className="thread-memories-header">
        <div>
          <Brain size={16} strokeWidth={1.8} aria-hidden="true" />
          <div><strong>会话记忆</strong><span>仅当前会话可见</span></div>
        </div>
        <button type="button" className="workspace-entry-icon" disabled={memories.isFetching} onClick={() => void memories.refetch()} aria-label="刷新记忆" title="刷新记忆">
          <RefreshCw size={13} aria-hidden="true" />
        </button>
      </header>

      {selectedSlug === null ? (
        <div className="thread-memory-list">
          {memories.isPending && <div className="thread-memory-state">正在加载记忆…</div>}
          {memories.isError && <div role="alert" className="thread-memory-state error">记忆加载失败：{errorMessage(memories.error)}</div>}
          {!memories.isPending && !memories.isError && items.length === 0 && (
            <div className="thread-memory-state"><Brain size={26} strokeWidth={1.3} aria-hidden="true" /><span>这个会话还没有可管理的记忆。</span></div>
          )}
          {items.map(memory => <MemoryRow key={memory.slug} memory={memory} onOpen={() => setSelectedSlug(memory.slug)} />)}
        </div>
      ) : (
        <div className="thread-memory-detail">
          <div className="thread-memory-detail-actions">
            <button type="button" className="thread-memory-back" onClick={() => setSelectedSlug(null)}><ChevronLeft size={14} aria-hidden="true" />返回列表</button>
            {selected && <button type="button" className="workspace-entry-icon danger" disabled={remove.isPending} onClick={() => setPendingDelete({ slug: selected.slug, name: selected.name })} aria-label="删除记忆" title="删除记忆"><Trash2 size={13} aria-hidden="true" /></button>}
          </div>
          {detail.isPending && <div className="thread-memory-state">正在加载记忆详情…</div>}
          {detail.isError && <div role="alert" className="thread-memory-state error">记忆详情加载失败：{errorMessage(detail.error)}</div>}
          {detail.data && (
            <article>
              <div className="thread-memory-meta"><span>{TYPE_LABEL[detail.data.type]}</span><time dateTime={detail.data.updated_at}>{updatedLabel(detail.data.updated_at)}</time></div>
              <h2>{detail.data.name}</h2>
              <p>{detail.data.description}</p>
              <pre>{detail.data.content}</pre>
            </article>
          )}
        </div>
      )}

      <ConfirmDialog
        open={pendingDelete !== null}
        title="删除记忆"
        message={`确认删除记忆“${pendingDelete?.name ?? ''}”？删除后无法恢复，后续分析也不会再召回它。`}
        confirmLabel="删除"
        danger
        onConfirm={() => {
          if (pendingDelete) remove.mutate(pendingDelete.slug)
          setPendingDelete(null)
        }}
        onCancel={() => setPendingDelete(null)}
      />
    </section>
  )
}

function MemoryRow({ memory, onOpen }: { memory: MemorySummary; onOpen: () => void }) {
  return (
    <button type="button" className="thread-memory-row" onClick={onOpen} aria-label={`查看记忆：${memory.name}`}>
      <div className="thread-memory-row-title"><strong>{memory.name}</strong><span>{TYPE_LABEL[memory.type]}</span></div>
      <p>{memory.description}</p>
      <time dateTime={memory.updated_at}>更新于 {updatedLabel(memory.updated_at)}</time>
    </button>
  )
}
