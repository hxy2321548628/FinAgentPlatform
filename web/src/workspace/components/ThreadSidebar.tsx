import { useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { createThread, deleteThread, listThreads, threadKeys, updateThread } from '../../api/threads'
import { errorMessage } from '../../api/request'
import { ConfirmDialog } from './ConfirmDialog'
import { useToast } from '../../components/ui/toast-context'
import { Skeleton } from '../../components/ui/Skeleton'

function threadLabel(title: string, createdAt: string): string {
  if (title) return title
  return `新对话 · ${new Date(createdAt).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })}`
}

export function ThreadSidebar() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { threadId } = useParams()
  const [hoveredId, setHoveredId] = useState<string | null>(null)
  const [pendingDelete, setPendingDelete] = useState<{ id: string; label: string } | null>(null)
  const [renaming, setRenaming] = useState<{ id: string; value: string } | null>(null)
  const threads = useInfiniteQuery({
    queryKey: threadKeys.list(),
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) => listThreads(pageParam),
    getNextPageParam: page => page.next_cursor ?? undefined,
  })
  const create = useMutation({
    mutationFn: createThread,
    async onSuccess(thread) {
      await queryClient.invalidateQueries({ queryKey: threadKeys.all })
      navigate(`/workspace/chat/${thread.id}`)
    },
    onError(error) {
      toast({ title: '创建会话失败', description: errorMessage(error), variant: 'error' })
    },
  })
  const remove = useMutation({
    mutationFn: deleteThread,
    async onSuccess(_, removedId) {
      await queryClient.invalidateQueries({ queryKey: threadKeys.all })
      if (threadId === removedId) navigate('/workspace/chat')
      toast({ title: '会话已删除', variant: 'success' })
    },
    onError(error) {
      toast({ title: '会话删除失败', description: errorMessage(error), variant: 'error' })
    },
  })
  const rename = useMutation({
    mutationFn: ({ id, title }: { id: string; title: string }) => updateThread(id, { title }),
    async onSuccess() {
      await queryClient.invalidateQueries({ queryKey: threadKeys.all })
      toast({ title: '会话已重命名', variant: 'success' })
    },
    onError(error) {
      toast({ title: '重命名失败', description: errorMessage(error), variant: 'error' })
    },
  })
  const items = threads.data?.pages.flatMap(page => page.items) ?? []

  // Enter 与 blur 可能先后都触发提交（输入框随状态卸载时浏览器会补一个 blur），
  // 用 ref 保证同一次重命名只提交一次
  const submittedRename = useRef<string | null>(null)
  const submitRename = () => {
    if (!renaming || submittedRename.current === renaming.id) return
    submittedRename.current = renaming.id
    const title = renaming.value.trim()
    setRenaming(null)
    if (title) rename.mutate({ id: renaming.id, title })
  }

  return (
    <div style={{ width: 240, flexShrink: 0, background: 'var(--surface)', borderRight: '1px solid var(--border)', display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      <div style={{ padding: '12px 12px 8px' }}>
        <button type="button" disabled={create.isPending} onClick={() => create.mutate()} style={{ width: '100%', padding: '8px 0', background: 'var(--action)', color: '#fff', border: 'none', borderRadius: 7, fontSize: 13, fontWeight: 500, cursor: 'pointer', fontFamily: 'inherit' }}>
          {create.isPending ? '正在创建…' : '＋ 新建分析'}
        </button>
      </div>
      <div style={{ padding: '4px 16px 8px', fontSize: 10, fontFamily: "'JetBrains Mono', monospace", textTransform: 'uppercase', letterSpacing: '0.2em', color: 'var(--text-muted)' }}>// HISTORY</div>
      <div style={{ flex: 1, overflowY: 'auto', padding: '0 8px 8px' }}>
        {threads.isPending && Array.from({ length: 3 }, (_, i) => <div key={i} style={{ padding: '10px 12px', marginBottom: 2, display: 'flex', flexDirection: 'column', gap: 6 }}><Skeleton width="80%" height={13} /><Skeleton width="45%" height={11} /></div>)}
        {threads.isError && <div role="alert" style={{ padding: 16, color: 'var(--danger)', fontSize: 12 }}>{errorMessage(threads.error)}</div>}
        {!threads.isPending && !threads.isError && items.length === 0 && <div style={{ padding: 16, color: 'var(--text-muted)', fontSize: 12 }}>还没有分析对话</div>}
        {items.map(thread => {
          const active = thread.id === threadId
          const hovered = thread.id === hoveredId
          const isRenaming = renaming?.id === thread.id
          return (
            <div key={thread.id} className="thread-row" onMouseEnter={() => setHoveredId(thread.id)} onMouseLeave={() => setHoveredId(null)} style={{ marginBottom: 2, background: active ? 'var(--action-light)' : hovered ? 'var(--bg)' : 'transparent', border: active ? '1px solid var(--action-border)' : '1px solid transparent', borderRadius: 7 }}>
              {isRenaming ? (
                <div style={{ padding: '8px 12px', display: 'flex', flexDirection: 'column', gap: 4 }}>
                  <input
                    autoFocus
                    aria-label="会话名称"
                    value={renaming.value}
                    maxLength={80}
                    onChange={event => setRenaming({ id: thread.id, value: event.target.value })}
                    onKeyDown={event => {
                      if (event.key === 'Enter') { event.preventDefault(); submitRename() }
                      if (event.key === 'Escape') setRenaming(null)
                    }}
                    onBlur={submitRename}
                    style={{ width: '100%', padding: '4px 8px', border: '1px solid var(--action-border)', borderRadius: 5, fontSize: 13, fontFamily: 'inherit', background: 'var(--surface)', color: 'var(--text-primary)', boxSizing: 'border-box' }}
                  />
                  <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>Enter 保存 · Esc 取消</div>
                </div>
              ) : (
                <>
                  <Link to={`/workspace/chat/${thread.id}`} aria-current={active ? 'page' : undefined} style={{ display: 'block', padding: '10px 12px', textDecoration: 'none' }}>
                    <div style={{ fontSize: 13, fontWeight: 500, color: active ? 'var(--action)' : 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', paddingRight: hovered ? 40 : 0 }}>{threadLabel(thread.title, thread.created_at)}</div>
                    <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>{new Date(thread.updated_at).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })}</div>
                  </Link>
                  <button type="button" className="thread-delete thread-rename" aria-label={`重命名${threadLabel(thread.title, thread.created_at)}`} disabled={rename.isPending} onClick={() => { submittedRename.current = null; setRenaming({ id: thread.id, value: thread.title }) }}>✎</button>
                  <button type="button" className="thread-delete" aria-label={`删除${threadLabel(thread.title, thread.created_at)}`} disabled={remove.isPending} onClick={() => setPendingDelete({ id: thread.id, label: threadLabel(thread.title, thread.created_at) })}>×</button>
                </>
              )}
            </div>
          )
        })}
        {threads.hasNextPage && <button type="button" disabled={threads.isFetchingNextPage} onClick={() => void threads.fetchNextPage()} style={{ width: '100%', padding: 8, border: 'none', background: 'transparent', color: 'var(--action)', cursor: 'pointer', fontSize: 12 }}>
          {threads.isFetchingNextPage ? '正在加载…' : '加载更早会话'}
        </button>}
      </div>

      <ConfirmDialog
        open={pendingDelete !== null}
        title="删除会话"
        message={`确认删除“${pendingDelete?.label ?? ''}”？此操作不可撤销。`}
        confirmLabel="删除"
        danger
        onConfirm={() => {
          if (pendingDelete) remove.mutate(pendingDelete.id)
          setPendingDelete(null)
        }}
        onCancel={() => setPendingDelete(null)}
      />
    </div>
  )
}
