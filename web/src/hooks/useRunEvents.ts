import { useEffect, useReducer, useRef, useState } from 'react'
import { isRetryableRunEventError, isTerminalStatus, subscribeToRunEvents } from '../api/events'
import { useRunEventTransport } from '../api/RunEventTransportContext'
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
  const [connectionError, setConnectionError] = useState<unknown>(null)
  const cursor = useRef<string | undefined>(undefined)
  const allowEmptyClose = useRef(isTerminalStatus(initialStatus))
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
    setConnectionError(null)
    dispatch({ kind: 'reset', status: initialStatus })
    // A run id identifies an independent Redis stream. Its cursor and accumulated
    // view must never leak into the next run rendered by the same hook instance.
    // initialStatus is intentionally excluded: cache refreshes must retain replayed output.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId])

  useEffect(() => {
    if (!transport || !enabled) return
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
  }, [enabled, runId, transport])

  return {
    ...state,
    connectionAvailable: transport !== null,
    connectionError,
    connectionRetryable: connectionError !== null && isRetryableRunEventError(connectionError),
    markApprovalSubmitted: () => dispatch({ kind: 'approval_submitted' }),
  }
}
