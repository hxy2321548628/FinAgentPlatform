import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { approveRun, cancelRun, getRun, listRuns, runKeys, submitRun } from '../../api/runs'
import { createThread, getThread, threadKeys, updateThread } from '../../api/threads'
import { fileKeys } from '../../api/files'
import { errorMessage } from '../../api/request'
import type { AgentConfig, Decision, RunHistory, RunStatus } from '../../api/types'
import { useRunEvents } from '../../hooks/useRunEvents'
import { isTerminalStatus } from '../../api/events'
import { takeHandedOffConfig } from '../pickedAgent'
import { ThreadSidebar } from '../components/ThreadSidebar'
import { MessageList } from '../components/MessageList'
import { TodoList } from '../components/TodoList'
import { ArtifactStrip } from '../components/ArtifactStrip'
import { ChatInput } from '../components/ChatInput'
import { WorkspaceFiles } from '../components/WorkspaceFiles'
import { ThreadMemories } from '../components/ThreadMemories'
import { Logo } from '../../components/Logo'

const LIVE_STATUS: readonly RunStatus[] = ['queued', 'running', 'waiting_approval']
const BOTTOM_FOLLOW_THRESHOLD = 32
const CHAT_HISTORY_WIDTH = 240
const FILES_PANEL_MIN_WIDTH = 320
const FILES_PANEL_INITIAL_WIDTH = 380
const FILES_PANEL_RESIZE_STEP = 32
/** 距视口 600px 就开始回放，滚到历史轮次前内容已经就位。 */
const REPLAY_ROOT_MARGIN = '600px 0px 600px 0px'

function statusLabel(status: RunStatus): string {
  return {
    queued: '排队中',
    running: '分析中',
    waiting_approval: '等待确认',
    succeeded: '已完成',
    failed: '失败',
    cancelled: '已取消',
  }[status]
}

function RunTurn({ run, threadId, onContentChange }: { run: RunHistory; threadId: string; onContentChange: () => void }) {
  const queryClient = useQueryClient()
  const sectionRef = useRef<HTMLElement>(null)
  const [replayRequested, setReplayRequested] = useState(false)
  const [reachedViewport, setReachedViewport] = useState(false)
  // **历史轮次默认全部可见**：滚进视口即自动回放（粘住不回退），不再要求逐条点击。
  // 运行中的那一轮始终在回放；IntersectionObserver 不可用时退化为立即回放。
  const live = LIVE_STATUS.includes(run.status)
  useEffect(() => {
    if (live || reachedViewport) return
    const node = sectionRef.current
    if (!node) return
    if (typeof IntersectionObserver === 'undefined') {
      setReachedViewport(true)
      return
    }
    const observer = new IntersectionObserver(entries => {
      if (entries.some(entry => entry.isIntersecting)) {
        setReachedViewport(true)
        observer.disconnect()
      }
    }, { rootMargin: REPLAY_ROOT_MARGIN })
    observer.observe(node)
    return () => observer.disconnect()
  }, [live, reachedViewport])
  const autoReplay = live || reachedViewport || replayRequested
  const view = useRunEvents(run.id, run.status, {
    enabled: autoReplay,
    resolveInterruptStatus: async () => (await getRun(run.id)).status,
    onTerminal() {
      void Promise.all([
        queryClient.invalidateQueries({ queryKey: runKeys.list(threadId) }),
        queryClient.invalidateQueries({ queryKey: threadKeys.all }),
        queryClient.invalidateQueries({ queryKey: fileKeys.tree(threadId) }),
      ])
    },
  })
  const approve = useMutation({
    mutationFn: (decisions: Decision[]) => approveRun(run.id, decisions),
    async onSuccess() {
      view.markApprovalSubmitted()
      await queryClient.invalidateQueries({ queryKey: runKeys.all })
    },
  })

  useLayoutEffect(() => {
    onContentChange()
  }, [onContentChange, view.items, view.pendingActions, view.status, view.todos])

  const submitDecisions = async (decisions: Decision[]) => {
    await approve.mutateAsync(decisions)
  }

  return <section ref={sectionRef} data-run-id={run.id} className="run-turn" style={{ padding: '18px 0 22px', borderBottom: '1px solid var(--border-light)' }}>
    <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}>
      <div style={{ maxWidth: 620 }}>
        <div style={{ padding: '11px 15px', borderRadius: '12px 12px 2px 12px', background: 'var(--brand)', color: '#fff', fontSize: 14, lineHeight: 1.65 }}>{run.content ?? '（这条历史提问未保留原文）'}</div>
      </div>
    </div>
    <TodoList todos={view.todos} />
    <MessageList items={view.items} pendingActions={view.pendingActions} onApprove={submitDecisions} threadId={threadId} live={LIVE_STATUS.includes(view.status)} />
    {isTerminalStatus(view.status) && <ArtifactStrip threadId={threadId} startedAt={run.started_at} />}
    {approve.isError && <div role="alert" style={{ margin: '8px 0 0 44px', color: 'var(--danger)', fontSize: 12 }}>{errorMessage(approve.error)}</div>}
    {!view.connectionAvailable && LIVE_STATUS.includes(view.status) && <div style={{ margin: '8px 0 0 44px', color: 'var(--text-muted)', fontSize: 11 }}>事件流传输层待接入；REST 主链路已建立。</div>}
    {!autoReplay && view.items.length === 0 && !LIVE_STATUS.includes(view.status) && view.connectionAvailable && !replayRequested && <button type="button" onClick={() => setReplayRequested(true)} style={{ margin: '8px 0 0 44px', padding: 0, border: 'none', background: 'transparent', color: 'var(--action)', cursor: 'pointer', fontSize: 11 }}>查看本轮回答与过程</button>}
    {Boolean(view.connectionError) && <div role="alert" style={{ margin: '8px 0 0 44px', color: 'var(--danger)', fontSize: 12 }}>{view.connectionRetryable ? '事件流连接中断，正在等待传输层重连。' : '事件流连接失败，请刷新页面后重试。'}</div>}
    <div style={{ margin: '9px 0 0 44px', color: view.status === 'failed' ? 'var(--danger)' : 'var(--text-muted)', fontSize: 11 }}>
      {statusLabel(view.status)}{run.error_message ? ` · ${run.error_message}` : ''}
    </div>
  </section>
}

export function Chat() {
  const { threadId } = useParams()
  const navigate = useNavigate()
  // 能力目录「使用」交接过来的配置。挂载时即取走，让欢迎页输入区直接预填。
  const [pickedAgentConfig] = useState<AgentConfig | undefined>(() => takeHandedOffConfig())
  const pickedConfigKey = JSON.stringify(pickedAgentConfig ?? {})
  const queryClient = useQueryClient()
  const [panelVisible, setPanelVisible] = useState(false)
  const [panelMountedThread, setPanelMountedThread] = useState<string | null>(null)
  const [panelView, setPanelView] = useState<'files' | 'memories'>('files')
  const [panelWidth, setPanelWidth] = useState(FILES_PANEL_INITIAL_WIDTH)
  const [panelResizing, setPanelResizing] = useState(false)
  const chatRoot = useRef<HTMLDivElement>(null)
  const panelWidthRef = useRef(FILES_PANEL_INITIAL_WIDTH)
  const panelResizeStart = useRef({ x: 0, width: FILES_PANEL_INITIAL_WIDTH })
  const panelWidthAdjusted = useRef(false)
  const panelThread = useRef(threadId)
  const scrollRegion = useRef<HTMLDivElement>(null)
  const followLatest = useRef(true)
  const initializedThread = useRef<string | undefined>(undefined)
  const thread = useQuery({
    queryKey: threadKeys.detail(threadId ?? ''),
    queryFn: () => getThread(threadId ?? ''),
    enabled: Boolean(threadId),
  })
  const runs = useInfiniteQuery({
    queryKey: runKeys.list(threadId ?? ''),
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) => listRuns(threadId ?? '', pageParam),
    getNextPageParam: page => page.next_cursor ?? undefined,
    enabled: Boolean(threadId),
  })
  const chronological = (runs.data?.pages.flatMap(page => page.items) ?? []).toReversed()
  const latestLive = chronological.findLast(run => LIVE_STATUS.includes(run.status))

  const scrollToLatest = useCallback((force = false) => {
    const element = scrollRegion.current
    if (!element || (!force && !followLatest.current)) return
    element.scrollTop = element.scrollHeight
  }, [])

  const panelWidthBounds = useCallback(() => {
    const rootWidth = chatRoot.current?.getBoundingClientRect().width || window.innerWidth
    const max = Math.max(24, rootWidth - CHAT_HISTORY_WIDTH)
    return { min: Math.min(FILES_PANEL_MIN_WIDTH, max), max }
  }, [])

  const updatePanelWidth = useCallback((width: number, adjusted = false) => {
    const { min, max } = panelWidthBounds()
    const next = Math.min(max, Math.max(min, width))
    panelWidthRef.current = next
    setPanelWidth(next)
    if (adjusted) panelWidthAdjusted.current = true
  }, [panelWidthBounds])

  useEffect(() => {
    if (!panelResizing) return
    const handlePointerMove = (event: PointerEvent) => {
      event.preventDefault()
      updatePanelWidth(panelResizeStart.current.width + panelResizeStart.current.x - event.clientX, true)
    }
    const handlePointerUp = () => setPanelResizing(false)
    window.addEventListener('pointermove', handlePointerMove)
    window.addEventListener('pointerup', handlePointerUp)
    window.addEventListener('pointercancel', handlePointerUp)
    return () => {
      window.removeEventListener('pointermove', handlePointerMove)
      window.removeEventListener('pointerup', handlePointerUp)
      window.removeEventListener('pointercancel', handlePointerUp)
    }
  }, [panelResizing, updatePanelWidth])

  useEffect(() => {
    const handleResize = () => updatePanelWidth(panelWidthRef.current)
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [updatePanelWidth])

  useEffect(() => {
    if (panelThread.current === threadId) return
    panelThread.current = threadId
    setPanelVisible(false)
    setPanelMountedThread(null)
    setPanelView('files')
    setPanelResizing(false)
    setPanelWidth(FILES_PANEL_INITIAL_WIDTH)
    panelWidthRef.current = FILES_PANEL_INITIAL_WIDTH
    panelWidthAdjusted.current = false
  }, [threadId])

  const togglePanel = () => {
    if (panelVisible) {
      setPanelVisible(false)
      return
    }
    setPanelMountedThread(threadId ?? null)
    if (panelWidthAdjusted.current) updatePanelWidth(panelWidthRef.current)
    else updatePanelWidth(panelWidthBounds().max)
    setPanelVisible(true)
  }

  useLayoutEffect(() => {
    if (!panelVisible || panelWidthAdjusted.current) return
    updatePanelWidth(panelWidthBounds().max)
  }, [panelVisible, panelWidthBounds, updatePanelWidth])

  const handlePanelResizeKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    const { min, max } = panelWidthBounds()
    const target = event.key === 'ArrowLeft' ? panelWidthRef.current + FILES_PANEL_RESIZE_STEP
      : event.key === 'ArrowRight' ? panelWidthRef.current - FILES_PANEL_RESIZE_STEP
        : event.key === 'Home' ? min
          : event.key === 'End' ? max
            : null
    if (target === null) return
    event.preventDefault()
    updatePanelWidth(target, true)
  }

  useLayoutEffect(() => {
    if (!threadId) {
      initializedThread.current = undefined
      followLatest.current = true
      return
    }
    if (runs.isPending || initializedThread.current === threadId) return
    initializedThread.current = threadId
    followLatest.current = true
    scrollToLatest(true)
  }, [runs.isPending, scrollToLatest, threadId])

  const submit = useMutation({
    mutationFn: async ({ text, agentConfig }: { text: string; agentConfig: AgentConfig | undefined }) => {
      // **欢迎页懒创建**：进入 /workspace/chat 不建会话，第一次发送才建 —— 点
      // 「新建分析」只是导航，天然幂等，也不会留下一堆空会话。提交成功才跳转，
      // 失败时留在欢迎页保住草稿。会话级配置在创建时一并写入（ChatInput 在有
      // 会话时自己写，欢迎页这条路径由这里补上）
      if (!threadId) {
        const created = await createThread()
        if (agentConfig !== undefined) {
          try {
            await updateThread(created.id, { agent_config: agentConfig })
          } catch {
            // 本轮仍带着这份配置提交，只是会话默认没存上 —— 不阻断发送
          }
        }
        const run = await submitRun(created.id, text, agentConfig)
        navigate(`/workspace/chat/${created.id}`, { replace: true })
        return run
      }
      return submitRun(threadId, text, agentConfig)
    },
    async onSuccess() {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: runKeys.all }),
        queryClient.invalidateQueries({ queryKey: threadKeys.all }),
      ])
    },
  })
  const cancel = useMutation({
    mutationFn: (runId: string) => cancelRun(runId),
    async onSuccess() {
      await queryClient.invalidateQueries({ queryKey: runKeys.list(threadId ?? '') })
    },
  })

  return <div ref={chatRoot} className={`chat-root${panelResizing ? ' resizing-files' : ''}`} style={{ display: 'flex', height: '100%', overflow: 'hidden' }}>
    <ThreadSidebar />
    <div className="chat-main">
      {threadId && <Logo className="chat-watermark" height={250} />}
      <div ref={scrollRegion} className="chat-scroll-region" data-testid="chat-scroll-region" onScroll={event => {
        const element = event.currentTarget
        followLatest.current = element.scrollHeight - element.scrollTop - element.clientHeight <= BOTTOM_FOLLOW_THRESHOLD
      }} style={{ padding: threadId ? '0 28px' : 0 }}>
        {!threadId && (
          <div className="chat-welcome">
            <Logo className="chat-welcome-logo" height={58} />
            <h1>开始一次新的分析</h1>
            <p>输入你的分析需求，智能体将自行编写 Python、在隔离沙箱中执行，并返回结论与图表 —— 不需要你会写代码。</p>
          </div>
        )}
        {thread.isError && <div role="alert" style={{ padding: 24, color: 'var(--danger)' }}>{errorMessage(thread.error)}</div>}
        {runs.isPending && threadId && <div style={{ padding: 24, color: 'var(--text-muted)' }}>正在加载对话历史…</div>}
        {runs.isError && <div role="alert" style={{ padding: 24, color: 'var(--danger)' }}>{errorMessage(runs.error)}</div>}
        {runs.hasNextPage && <button type="button" disabled={runs.isFetchingNextPage} onClick={() => void runs.fetchNextPage()} style={{ display: 'block', margin: '12px auto', border: 'none', background: 'transparent', color: 'var(--action)', cursor: 'pointer' }}>{runs.isFetchingNextPage ? '正在加载…' : '加载更早记录'}</button>}
        {threadId && !runs.isPending && chronological.length === 0 && <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>这个对话还没有提问。</div>}
        {threadId && chronological.map(run => <RunTurn key={run.id} run={run} threadId={threadId} onContentChange={scrollToLatest} />)}
        {submit.isError && <div role="alert" style={{ padding: '8px 0', color: 'var(--danger)', fontSize: 12 }}>{errorMessage(submit.error)}</div>}
      </div>
      {threadId ? (
        <ChatInput key={`${threadId}:${pickedConfigKey}`} disabled={submit.isPending} isRunning={Boolean(latestLive)} threadId={threadId} threadAgentConfig={thread.data?.agent_config} initialAgentConfig={pickedAgentConfig} onSend={async (text, agentConfig) => { await submit.mutateAsync({ text, agentConfig }) }} onStop={() => latestLive && cancel.mutate(latestLive.id)} />
      ) : (
        <div className="chat-welcome-composer">
          <ChatInput key={`welcome:${pickedConfigKey}`} disabled={submit.isPending} isRunning={Boolean(latestLive)} threadAgentConfig={thread.data?.agent_config} initialAgentConfig={pickedAgentConfig} onSend={async (text, agentConfig) => { await submit.mutateAsync({ text, agentConfig }) }} onStop={() => latestLive && cancel.mutate(latestLive.id)} />
        </div>
      )}
    </div>
    {threadId && (
      <aside
        className={`chat-files-panel${panelVisible ? '' : ' collapsed'}${panelResizing ? ' resizing' : ''}`}
        aria-label="会话工作区"
        style={{ '--chat-files-width': `${panelWidth}px` } as React.CSSProperties}
      >
        {panelVisible && (
          <div
            className="chat-files-resizer"
            role="separator"
            aria-label="调整工作区宽度"
            aria-orientation="vertical"
            aria-valuemin={Math.round(panelWidthBounds().min)}
            aria-valuemax={Math.round(panelWidthBounds().max)}
            aria-valuenow={Math.round(panelWidth)}
            tabIndex={0}
            title="拖动调整宽度；双击展开到最大"
            onDoubleClick={() => updatePanelWidth(panelWidthBounds().max, true)}
            onPointerDown={event => {
              if (event.button !== 0) return
              event.preventDefault()
              panelResizeStart.current = { x: event.clientX, width: panelWidthRef.current }
              setPanelResizing(true)
            }}
            onKeyDown={handlePanelResizeKeyDown}
          />
        )}
        <button
          type="button"
          className="chat-files-toggle"
          aria-label={panelVisible ? '收起工作区' : '展开工作区'}
          aria-expanded={panelVisible}
          onClick={togglePanel}
          title={panelVisible ? '收起工作区' : '展开工作区'}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><polyline points={panelVisible ? '9 18 15 12 9 6' : '15 18 9 12 15 6'} /></svg>
        </button>
        {panelMountedThread === threadId && (
          <div className="chat-files-content" hidden={!panelVisible}>
            <div className="chat-workspace-tabs" role="tablist" aria-label="会话工作区视图">
              <button id="chat-files-tab" type="button" role="tab" aria-controls="chat-files-tabpanel" aria-selected={panelView === 'files'} onClick={() => setPanelView('files')}>文件</button>
              <button id="chat-memories-tab" type="button" role="tab" aria-controls="chat-memories-tabpanel" aria-selected={panelView === 'memories'} onClick={() => setPanelView('memories')}>记忆</button>
            </div>
            <div
              id={panelView === 'files' ? 'chat-files-tabpanel' : 'chat-memories-tabpanel'}
              className="chat-workspace-view"
              role="tabpanel"
              aria-labelledby={panelView === 'files' ? 'chat-files-tab' : 'chat-memories-tab'}
              hidden={!panelVisible}
            >
              {panelView === 'files' ? (
                <WorkspaceFiles threadId={threadId} title={thread.data?.title || '新分析'} compact />
              ) : (
                <ThreadMemories threadId={threadId} />
              )}
            </div>
          </div>
        )}
      </aside>
    )}
  </div>
}
