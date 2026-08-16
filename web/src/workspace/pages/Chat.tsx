import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { approveRun, cancelRun, getRun, listRuns, runKeys, submitRun } from '../../api/runs'
import { getThread, threadKeys } from '../../api/threads'
import { fileKeys } from '../../api/files'
import { errorMessage } from '../../api/request'
import type { AgentConfig, Decision, RunHistory, RunStatus } from '../../api/types'
import { useRunEvents } from '../../hooks/useRunEvents'
import { isTerminalStatus } from '../../api/events'
import { describeAgentConfig } from '../config'
import { takeHandedOffAgent } from '../pickedAgent'
import { ThreadSidebar } from '../components/ThreadSidebar'
import { MessageList } from '../components/MessageList'
import { ArtifactStrip } from '../components/ArtifactStrip'
import { ChatInput } from '../components/ChatInput'
import { WorkspaceFiles } from '../components/WorkspaceFiles'

const LIVE_STATUS: readonly RunStatus[] = ['queued', 'running', 'waiting_approval']
const BOTTOM_FOLLOW_THRESHOLD = 32

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

function RunTurn({ run, threadId, autoReplay, onContentChange }: { run: RunHistory; threadId: string; autoReplay: boolean; onContentChange: () => void }) {
  const queryClient = useQueryClient()
  const [replayRequested, setReplayRequested] = useState(false)
  const view = useRunEvents(run.id, run.status, {
    enabled: autoReplay || replayRequested,
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
  // **引用要说清是谁的哪一版**：只说「使用了一个智能体」的话，作者发了新版本之后，
  // 历史那几轮到底按哪一版跑的就再也说不清了
  const configuration = describeAgentConfig(run.agent_config)
  const roleLabel = run.agent_config?.agent_id
    ? configuration.split('\n', 1)[0]
    : configuration === '平台默认配置'
      ? configuration
      : '自定义提示词'
  const skillCount = run.agent_config?.skills?.length ?? 0
  const configurationLabel = skillCount > 0 ? `${roleLabel} · ${skillCount} 个 Skill` : roleLabel

  useLayoutEffect(() => {
    onContentChange()
  }, [onContentChange, view.items, view.pendingActions, view.status])

  const submitDecisions = async (decisions: Decision[]) => {
    await approve.mutateAsync(decisions)
  }

  return <section className="run-turn" style={{ padding: '18px 0 22px', borderBottom: '1px solid var(--border-light)' }}>
    <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}>
      <div style={{ maxWidth: 620 }}>
        <div style={{ padding: '11px 15px', borderRadius: '12px 12px 2px 12px', background: 'var(--brand)', color: '#fff', fontSize: 14, lineHeight: 1.65 }}>{run.content ?? '（这条历史提问未保留原文）'}</div>
        <details style={{ marginTop: 5, textAlign: 'right', color: 'var(--text-muted)', fontSize: 11 }}>
          <summary style={{ cursor: 'pointer' }}>本轮配置：{configurationLabel}</summary>
          <div style={{ marginTop: 5, padding: 8, maxWidth: 500, whiteSpace: 'pre-wrap', textAlign: 'left', border: '1px solid var(--border)', borderRadius: 5, background: 'var(--surface)' }}>{configuration}</div>
        </details>
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
  // 广场「用它开始分析」交接过来的那个 agent，配置面板据此预设成引用它。
  // **要等有会话了才取**：从广场跳过来时多半还没有会话，那时取走就白丢了
  const [pickedAgentId, setPickedAgentId] = useState<string | undefined>(undefined)
  const queryClient = useQueryClient()
  const [panelVisible, setPanelVisible] = useState(true)
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
  const autoReplayRun = latestLive ?? chronological.at(-1)

  useEffect(() => {
    if (!threadId) return
    const handed = takeHandedOffAgent()
    if (handed) setPickedAgentId(handed)
  }, [threadId])

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
    mutationFn: ({ text, agentConfig }: { text: string; agentConfig: AgentConfig | undefined }) => {
      if (!threadId) throw new Error('请先新建一个分析对话')
      return submitRun(threadId, text, agentConfig)
    },
    async onSuccess() {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: runKeys.list(threadId ?? '') }),
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
    <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden', background: 'var(--bg)' }}>
      <header style={{ minHeight: 54, padding: '10px 24px', boxSizing: 'border-box', borderBottom: '1px solid var(--border)', background: 'var(--surface)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
        <div style={{ minWidth: 0 }}><div style={{ fontSize: 14, fontWeight: 650, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{threadId ? thread.data?.title || '新分析' : '选择或新建分析'}</div></div>
        {threadId && <button type="button" onClick={() => setPanelVisible(value => !value)} style={{ border: '1px solid var(--border)', borderRadius: 5, background: 'var(--surface)', color: 'var(--text-secondary)', padding: '5px 9px', cursor: 'pointer', fontSize: 11 }}>{panelVisible ? '收起工作目录' : '展开工作目录'}</button>}
      </header>
      <div ref={scrollRegion} data-testid="chat-scroll-region" onScroll={event => {
        const element = event.currentTarget
        followLatest.current = element.scrollHeight - element.scrollTop - element.clientHeight <= BOTTOM_FOLLOW_THRESHOLD
      }} style={{ flex: 1, overflowY: 'auto', padding: '0 28px' }}>
        {!threadId && <div style={{ height: '100%', display: 'grid', placeItems: 'center', color: 'var(--text-muted)', fontSize: 14 }}>点击左侧“新建分析”开始。</div>}
        {thread.isError && <div role="alert" style={{ padding: 24, color: 'var(--danger)' }}>{errorMessage(thread.error)}</div>}
        {runs.isPending && threadId && <div style={{ padding: 24, color: 'var(--text-muted)' }}>正在加载对话历史…</div>}
        {runs.isError && <div role="alert" style={{ padding: 24, color: 'var(--danger)' }}>{errorMessage(runs.error)}</div>}
        {runs.hasNextPage && <button type="button" disabled={runs.isFetchingNextPage} onClick={() => void runs.fetchNextPage()} style={{ display: 'block', margin: '12px auto', border: 'none', background: 'transparent', color: 'var(--action)', cursor: 'pointer' }}>{runs.isFetchingNextPage ? '正在加载…' : '加载更早记录'}</button>}
        {threadId && !runs.isPending && chronological.length === 0 && <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>这个对话还没有提问。</div>}
        {chronological.map(run => <RunTurn key={run.id} run={run} threadId={threadId ?? ''} autoReplay={run.id === autoReplayRun?.id} onContentChange={scrollToLatest} />)}
        {submit.isError && <div role="alert" style={{ padding: '8px 0', color: 'var(--danger)', fontSize: 12 }}>{errorMessage(submit.error)}</div>}
      </div>
      <ChatInput key={pickedAgentId ?? 'default'} disabled={!threadId || submit.isPending} isRunning={Boolean(latestLive)} threadAgentConfig={thread.data?.agent_config} initialAgentId={pickedAgentId} onSend={async (text, agentConfig) => { await submit.mutateAsync({ text, agentConfig }) }} onStop={() => latestLive && cancel.mutate(latestLive.id)} />
    </div>
    {panelVisible && threadId && <aside className="chat-files-panel" style={{ flexShrink: 0, borderLeft: '1px solid var(--border)', overflow: 'hidden' }}><WorkspaceFiles threadId={threadId} title={thread.data?.title || '新分析'} compact /></aside>}
  </div>
}
