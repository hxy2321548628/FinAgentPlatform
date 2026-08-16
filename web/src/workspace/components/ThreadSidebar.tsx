import { useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { deleteThread, listThreads, threadKeys, updateThread } from '../../api/threads'
import { errorMessage } from '../../api/request'
import { ConfirmDialog } from './ConfirmDialog'
import { useToast } from '../../components/ui/toast-context'
import { Skeleton } from '../../components/ui/Skeleton'
import { Button } from '../../components/ui/Button'
import * as DropdownMenu from '@radix-ui/react-dropdown-menu'

function threadLabel(title: string, createdAt: string): string {
  if (title) return title
  return `新对话 · ${new Date(createdAt).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })}`
}

const LIVE_LABEL = { queued: '排队中', running: '分析中', waiting_approval: '等待确认' } as const

export function ThreadSidebar() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { threadId } = useParams()
  const [hoveredId, setHoveredId] = useState<string | null>(null)
  const [pendingDelete, setPendingDelete] = useState<{ id: string; label: string } | null>(null)
  const [renaming, setRenaming] = useState<{ id: string; value: string } | null>(null)
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  // 输入停顿 300ms 才发搜索请求：每个字符一次请求对接口毫无必要
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search.trim()), 300)
    return () => clearTimeout(timer)
  }, [search])
  const threads = useInfiniteQuery({
    queryKey: threadKeys.list(debouncedSearch),
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) => listThreads(pageParam, 20, debouncedSearch),
    getNextPageParam: page => page.next_cursor ?? undefined,
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
      <div style={{ padding: '14px 16px 8px', fontSize: 10, fontFamily: "'JetBrains Mono', monospace", textTransform: 'uppercase', letterSpacing: '0.2em', color: 'var(--text-muted)' }}>// HISTORY</div>
      <div style={{ padding: '0 12px 8px' }}>
        <Button style={{ width: '100%' }} onClick={() => navigate('/workspace/chat')}>
          ＋ 新建分析
        </Button>
      </div>
      <div className="thread-search">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></svg>
        <input type="search" placeholder="搜索会话" aria-label="搜索会话" value={search} onChange={event => setSearch(event.target.value)} />
        {search && <button type="button" aria-label="清空搜索" onClick={() => setSearch('')}>×</button>}
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: '0 8px 8px' }}>
        {threads.isPending && Array.from({ length: 3 }, (_, i) => <div key={i} style={{ padding: '10px 12px', marginBottom: 2, display: 'flex', flexDirection: 'column', gap: 6 }}><Skeleton width="80%" height={13} /><Skeleton width="45%" height={11} /></div>)}
        {threads.isError && <div role="alert" style={{ padding: 16, color: 'var(--danger)', fontSize: 12 }}>{errorMessage(threads.error)}</div>}
        {!threads.isPending && !threads.isError && items.length === 0 && (
          <div style={{ padding: 16, color: 'var(--text-muted)', fontSize: 12 }}>
            {debouncedSearch ? `没有匹配“${debouncedSearch}”的会话` : '还没有分析对话'}
          </div>
        )}
        {items.map(thread => {
          const active = thread.id === threadId
          const hovered = thread.id === hoveredId
          const isRenaming = renaming?.id === thread.id
          const label = threadLabel(thread.title, thread.created_at)
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
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
                      {thread.live_run_status && <span className="thread-live-dot" aria-hidden="true" />}
                      <div style={{ minWidth: 0, fontSize: 13, fontWeight: 500, color: active ? 'var(--action)' : 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', paddingRight: hovered ? 32 : 0 }}>{label}</div>
                    </div>
                    <div style={{ fontSize: 11, color: thread.live_run_status ? 'var(--status-active)' : 'var(--text-muted)', marginTop: 4 }}>
                      {thread.live_run_status ? LIVE_LABEL[thread.live_run_status as keyof typeof LIVE_LABEL] : new Date(thread.updated_at).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })}
                    </div>
                  </Link>
                  <DropdownMenu.Root>
                    <DropdownMenu.Trigger asChild>
                      <button type="button" className="thread-more" aria-label={`会话操作：${label}`}>
                        <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><circle cx="12" cy="5" r="1.6"/><circle cx="12" cy="12" r="1.6"/><circle cx="12" cy="19" r="1.6"/></svg>
                      </button>
                    </DropdownMenu.Trigger>
                    <DropdownMenu.Portal>
                      <DropdownMenu.Content className="theme-menu" align="end" sideOffset={2}>
                        <DropdownMenu.Item className="theme-menu-item" onSelect={() => { submittedRename.current = null; setRenaming({ id: thread.id, value: thread.title }) }}>
                          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><path d="M17 3a2.85 2.85 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/></svg>
                          重命名
                        </DropdownMenu.Item>
                        <DropdownMenu.Item className="theme-menu-item thread-menu-danger" onSelect={() => setPendingDelete({ id: thread.id, label })}>
                          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m3 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/></svg>
                          删除
                        </DropdownMenu.Item>
                      </DropdownMenu.Content>
                    </DropdownMenu.Portal>
                  </DropdownMenu.Root>
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
