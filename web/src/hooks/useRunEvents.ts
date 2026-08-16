import { useEffect, useReducer, useRef, useState } from 'react'
import { isRetryableRunEventError, isTerminalStatus, subscribeToRunEvents } from '../api/events'
import { useRunEventTransport } from '../api/RunEventTransportContext'
import { fetchRunReplay } from '../api/runs'
import type { RunStatus } from '../api/types'
import { createRunViewState, runViewReducer } from '../workspace/eventReducer'

interface UseRunEventsOptions {
  enabled?: boolean
  onTerminal?: (status: Extract<RunStatus, 'succeeded' | 'failed' | 'cancelled'>) => void
  resolveInterruptStatus?: () => Promise<RunStatus>
}

function eventIdParts(value: string): readonly [bigint, bigint] | null {
  const matched = /^(\d+)-(\d+)$/.exec(value)
  if (!matched?.[1] || !matched[2]) return null
  return [BigInt(matched[1]), BigInt(matched[2])]
}

function eventWasApplied(eventId: string, cursor: string | undefined): boolean {
  if (!cursor) return false
  if (eventId === cursor) return true
  // Redis Stream IDs are numeric pairs: lexical order gets 10-0 and 9-0 backwards.
  const candidate = eventIdParts(eventId)
  const current = eventIdParts(cursor)
  if (!candidate || !current) return false
  return candidate[0] < current[0]
    || (candidate[0] === current[0] && candidate[1] <= current[1])
}

export function useRunEvents(runId: string, initialStatus: RunStatus, options: UseRunEventsOptions = {}) {
  const transport = useRunEventTransport()
  const enabled = options.enabled ?? true
  const [state, dispatch] = useReducer(runViewReducer, initialStatus, createRunViewState)
  const terminal = isTerminalStatus(state.status)
  const [connectionError, setConnectionError] = useState<unknown>(null)
  const cursor = useRef<string | undefined>(undefined)
  const allowEmptyClose = useRef(isTerminalStatus(initialStatus))
  // **挂载那一刻**它是不是已经结束了。跑着跑着结束的那一条不算 —— 它的事件
  // 已经从订阅里全收过了，再补一次一次性读取会把整轮回答渲染两遍。
  // 与 allowEmptyClose 同源，因此一起在换 run 时重算
  const replayOnly = useRef(isTerminalStatus(initialStatus))
  const onTerminalRef = useRef(options.onTerminal)
  const resolveInterruptStatusRef = useRef(options.resolveInterruptStatus)
  onTerminalRef.current = options.onTerminal
  resolveInterruptStatusRef.current = options.resolveInterruptStatus

  useEffect(() => {
    dispatch({ kind: 'status_synced', status: initialStatus })
  }, [initialStatus])

  useEffect(() => {
    cursor.current = undefined
    allowEmptyClose.current = isTerminalStatus(initialStatus)
    replayOnly.current = isTerminalStatus(initialStatus)
    setConnectionError(null)
    dispatch({ kind: 'reset', status: initialStatus })
    // A run id identifies an independent Redis stream. Its cursor and accumulated
    // view must never leak into the next run rendered by the same hook instance.
    // initialStatus is intentionally excluded: cache refreshes must retain replayed output.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId])

  useEffect(() => {
    if (!enabled) return
    // 已经结束的 run 一次读完就收工：它不会再有新事件，而订阅断了要重连，
    // 重连又要过一次频率闸 —— 一条反复重连的流足以把整个界面的额度吃光
    if (replayOnly.current) {
      let abandoned = false
      void fetchRunReplay(runId).then(replayed => {
        if (abandoned) return
        for (const one of replayed) {
          cursor.current = one.id
          dispatch({ kind: 'event', event: one.event })
        }
      }).catch(error => {
        if (!abandoned) setConnectionError(error)
      })
      return () => {
        abandoned = true
      }
    }

    // **它结束了就别再连。** 终态可能是从 runs 列表同步来的，事件流那边一条都没收到
    // （比如一直被拒），此时流仍在重连报错，而补齐逻辑又在清错误 —— 界面上就是红字
    // 一闪一闪。已经结束的 run 没有任何新事件值得等
    if (terminal) return

    if (!transport) return
    let connection: { close(): void } | null = null
    let closed = false
    const close = () => {
      if (closed) return
      closed = true
      connection?.close()
    }
    connection = subscribeToRunEvents(transport, runId, {
      cursor: cursor.current,
      allowEmptyClose: allowEmptyClose.current,
      onOpen() {
        setConnectionError(null)
      },
      onError(error) {
        setConnectionError(error)
      },
      onEvent(event, lastEventId) {
        if (lastEventId && eventWasApplied(lastEventId, cursor.current)) return
        if (lastEventId) {
          cursor.current = lastEventId
        }
        const resolveInterruptStatus = resolveInterruptStatusRef.current
        if (event.type === 'interrupt' && resolveInterruptStatus) {
          const isLatest = () => !closed && (!lastEventId || cursor.current === lastEventId)
          void resolveInterruptStatus().then(status => {
            if (!isLatest()) return
            if (status === 'waiting_approval') dispatch({ kind: 'event', event })
            else dispatch({ kind: 'status_synced', status })
          }).catch(() => {
            // 权威状态暂时查不到时仍展示审批，避免一次网络抖动让 run 永久卡住。
            if (isLatest()) dispatch({ kind: 'event', event })
          })
          return
        }
        dispatch({ kind: 'event', event })
        if (event.type === 'run.finished') {
          close()
          onTerminalRef.current?.('succeeded')
        } else if (event.type === 'run.failed') {
          close()
          onTerminalRef.current?.('failed')
        } else if (event.type === 'run.cancelled') {
          close()
          onTerminalRef.current?.('cancelled')
        }
      },
    })
    return close
  }, [enabled, runId, terminal, transport])

  // 断过线的那一轮走到终态之后，一次性补齐并把提示收掉。**不能只把话删掉** ——
  // 断线期间的那段内容是真的可能缺，界面会停在断线那一刻。而「正在等待重连」
  // 对一个已经结束的 run 是假话：它不会再重连了
  useEffect(() => {
    if (replayOnly.current || connectionError === null || !isTerminalStatus(state.status)) return
    let abandoned = false
    void fetchRunReplay(runId).then(replayed => {
      if (abandoned) return
      dispatch({ kind: 'reset', status: state.status })
      for (const one of replayed) {
        cursor.current = one.id
        dispatch({ kind: 'event', event: one.event })
      }
      setConnectionError(null)
    }).catch(() => undefined)
    return () => {
      abandoned = true
    }
  }, [connectionError, runId, state.status])

  return {
    ...state,
    connectionAvailable: transport !== null,
    connectionError,
    // 一次性读取失败时**不算可重连** —— 它没有重连这回事，
    // 而调用方拿这个值在「等着自己恢复」与「请刷新」两句话之间选
    connectionRetryable: !replayOnly.current
      && connectionError !== null
      && isRetryableRunEventError(connectionError),
    markApprovalSubmitted: () => dispatch({ kind: 'approval_submitted' }),
  }
}
