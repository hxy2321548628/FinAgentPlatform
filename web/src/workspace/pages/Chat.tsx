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
import { takeHandedOffAgent } from '../pickedAgent'
import { ThreadSidebar } from '../components/ThreadSidebar'
import { MessageList } from '../components/MessageList'
import { ArtifactStrip } from '../components/ArtifactStrip'
import { ChatInput } from '../components/ChatInput'
import { WorkspaceFiles } from '../components/WorkspaceFiles'
import { Logo } from '../../components/Logo'

const LIVE_STATUS: readonly RunStatus[] = ['queued', 'running', 'waiting_approval']
const BOTTOM_FOLLOW_THRESHOLD = 32
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
  }, [onContentChange, view.items, view.pendingActions, view.status])

  const submitDecisions = async (decisions: Decision[]) => {
    await approve.mutateAsync(decisions)
  }

  return <section ref={sectionRef} data-run-id={run.id} className="run-turn" style={{ padding: '18px 0 22px', borderBottom: '1px solid var(--border-light)' }}>
    <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}>
      <div style={{ maxWidth: 620 }}>
        <div style={{ padding: '11px 15px', borderRadius: '12px 12px 2px 12px', background: 'var(--brand)', color: '#fff', fontSize: 14, lineHeight: 1.65 }}>{run.content ?? '（这条历史提问未保留原文）'}</div>
      </div>
    </div>
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
  // 广场「用它开始分析」交接过来的那个 agent，配置面板据此预设成引用它。
  // 挂载时即取走：懒创建下这时可能还没有会话，取走正好让欢迎页的输入区带着它
  const [pickedAgentId] = useState<string | undefined>(() => takeHandedOffAgent() ?? undefined)
  const queryClient = useQueryClient()
  const [panelVisible, setPanelVisible] = useState(false)
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

  return <div className="chat-root" style={{ display: 'flex', height: '100%', overflow: 'hidden' }}>
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
        <ChatInput key={`${threadId}:${pickedAgentId ?? ''}`} disabled={submit.isPending} isRunning={Boolean(latestLive)} threadId={threadId} threadAgentConfig={thread.data?.agent_config} initialAgentId={pickedAgentId} onSend={async (text, agentConfig) => { await submit.mutateAsync({ text, agentConfig }) }} onStop={() => latestLive && cancel.mutate(latestLive.id)} />
      ) : (
        <div className="chat-welcome-composer">
          <ChatInput key={`welcome:${pickedAgentId ?? ''}`} disabled={submit.isPending} isRunning={Boolean(latestLive)} threadAgentConfig={thread.data?.agent_config} initialAgentId={pickedAgentId} onSend={async (text, agentConfig) => { await submit.mutateAsync({ text, agentConfig }) }} onStop={() => latestLive && cancel.mutate(latestLive.id)} />
        </div>
      )}
    </div>
    {threadId && (
      <aside className={`chat-files-panel${panelVisible ? '' : ' collapsed'}`} aria-label="会话工作区">
        <button
          type="button"
          className="chat-files-toggle"
          aria-label={panelVisible ? '收起工作区' : '展开工作区'}
          aria-expanded={panelVisible}
          onClick={() => setPanelVisible(value => !value)}
          title={panelVisible ? '收起工作区' : '展开工作区'}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><polyline points={panelVisible ? '9 18 15 12 9 6' : '15 18 9 12 15 6'} /></svg>
        </button>
        {panelVisible && <div className="chat-files-content"><WorkspaceFiles threadId={threadId} title={thread.data?.title || '新分析'} compact /></div>}
      </aside>
    )}
  </div>
}
