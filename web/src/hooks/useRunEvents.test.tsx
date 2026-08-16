import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { RunEventTransportProvider } from '../api/RunEventTransportContext'
import type { RunEventConnectionOptions, RunEventTransport } from '../api/events'
import type { RunStatus } from '../api/types'
import { useRunEvents } from './useRunEvents'

const fetchRunReplayMock = vi.hoisted(() => vi.fn())

vi.mock('../api/runs', () => ({ fetchRunReplay: fetchRunReplayMock }))

function token(runId: string, text: string) {
  return JSON.stringify({ type: 'token', ts: 1, run_id: runId, path: [], data: { text } })
}

function replayedToken(runId: string, text: string, id = '100-0') {
  return { id, event: { type: 'token', ts: 1, run_id: runId, path: [], data: { text } } }
}

beforeEach(() => {
  fetchRunReplayMock.mockReset()
  fetchRunReplayMock.mockResolvedValue([])
})

function harness() {
  const options: RunEventConnectionOptions[] = []
  const closes: Array<ReturnType<typeof vi.fn>> = []
  const transport: RunEventTransport = {
    connect(received) {
      options.push(received)
      const close = vi.fn()
      closes.push(close)
      return { close }
    },
  }
  const wrapper = ({ children }: { children: React.ReactNode }) => <RunEventTransportProvider transport={transport}>{children}</RunEventTransportProvider>
  return { options, closes, wrapper }
}

describe('useRunEvents', () => {
  it('resets the cursor and accumulated output when runId changes', () => {
    const test = harness()
    const hook = renderHook(
      ({ runId }) => useRunEvents(runId, 'running'),
      { initialProps: { runId: 'run-a' }, wrapper: test.wrapper },
    )
    act(() => test.options[0].onMessage({ eventName: 'token', lastEventId: '100-0', data: token('run-a', 'A') }))
    expect(hook.result.current.items).toMatchObject([{ kind: 'answer', text: 'A' }])

    hook.rerender({ runId: 'run-b' })

    expect(test.closes[0]).toHaveBeenCalledOnce()
    expect(test.options[1]).toMatchObject({
      url: '/api/runs/run-b/events', cursor: undefined, allowEmptyClose: false,
    })
    expect(hook.result.current.items).toEqual([])
  })

  it('applies a repeated event id only once', () => {
    const test = harness()
    const hook = renderHook(() => useRunEvents('run-a', 'running'), { wrapper: test.wrapper })
    const message = { eventName: 'token', lastEventId: '100-0', data: token('run-a', '喵') }
    act(() => {
      test.options[0].onMessage(message)
      test.options[0].onMessage(message)
    })
    expect(hook.result.current.items).toMatchObject([{ kind: 'answer', text: '喵' }])
  })

  it('rejects replayed ids at or before the current cursor without retaining an id set', () => {
    const test = harness()
    const hook = renderHook(() => useRunEvents('run-a', 'running'), { wrapper: test.wrapper })

    act(() => {
      for (let index = 0; index < 257; index += 1) {
        test.options[0].onMessage({
          eventName: 'token', lastEventId: `${index}-0`, data: token('run-a', 'x'),
        })
      }
      test.options[0].onMessage({ eventName: 'token', lastEventId: '256-0', data: token('run-a', 'y') })
      // A lexical comparison would wrongly consider 99 newer than 256.
      test.options[0].onMessage({ eventName: 'token', lastEventId: '99-0', data: token('run-a', 'z') })
    })

    expect(hook.result.current.items).toMatchObject([{ kind: 'answer', text: 'x'.repeat(257) }])
  })

  // 已经结束的 run 不会再产生事件。**拿一条长连接去读一份不再变化的历史**，
  // 断了要重连，重连又消耗一个频率名额 —— 一条反复重连的流足以把界面额度吃光。
  it('reads a finished run in one request instead of holding a stream open', async () => {
    const test = harness()
    fetchRunReplayMock.mockResolvedValue([replayedToken('run-a', '结论是')])

    const hook = renderHook(() => useRunEvents('run-a', 'succeeded'), { wrapper: test.wrapper })

    await waitFor(() => expect(hook.result.current.items).toMatchObject([{ kind: 'answer', text: '结论是' }]))
    expect(fetchRunReplayMock).toHaveBeenCalledWith('run-a')
    expect(test.options).toHaveLength(0)
  })

  it('starts a finished run from empty state after a page remount', async () => {
    const test = harness()
    fetchRunReplayMock.mockResolvedValue([replayedToken('run-a', '旧页面')])
    const first = renderHook(() => useRunEvents('run-a', 'succeeded'), { wrapper: test.wrapper })
    await waitFor(() => expect(first.result.current.items).toMatchObject([{ kind: 'answer', text: '旧页面' }]))

    first.unmount()
    fetchRunReplayMock.mockResolvedValue([])
    const remounted = renderHook(() => useRunEvents('run-a', 'succeeded'), { wrapper: test.wrapper })

    expect(remounted.result.current.items).toEqual([])
    expect(test.options).toHaveLength(0)
  })

  it('still opens a stream for a run that has not finished', () => {
    const test = harness()

    renderHook(() => useRunEvents('run-a', 'running'), { wrapper: test.wrapper })

    expect(test.options).toHaveLength(1)
    expect(fetchRunReplayMock).not.toHaveBeenCalled()
  })

  // 跑着的那一条已经把事件全收过了。再补一次 REST 会把整轮回答渲染两遍
  it('does not re-fetch a run that finished while its stream was open', () => {
    const test = harness()
    const hook = renderHook(
      ({ status }: { status: RunStatus }) => useRunEvents('run-a', status),
      { initialProps: { status: 'running' as RunStatus }, wrapper: test.wrapper },
    )
    act(() => test.options[0].onMessage({ eventName: 'token', lastEventId: '100-0', data: token('run-a', '答') }))

    hook.rerender({ status: 'succeeded' })

    expect(fetchRunReplayMock).not.toHaveBeenCalled()
    expect(hook.result.current.items).toMatchObject([{ kind: 'answer', text: '答' }])
  })

  it('switching to a finished run reads it in one request', async () => {
    const test = harness()
    const hook = renderHook(
      ({ runId, status }: { runId: string; status: RunStatus }) => useRunEvents(runId, status),
      { initialProps: { runId: 'run-a', status: 'running' as RunStatus }, wrapper: test.wrapper },
    )
    expect(test.options).toHaveLength(1)
    fetchRunReplayMock.mockResolvedValue([replayedToken('run-b', '旧的那轮')])

    hook.rerender({ runId: 'run-b', status: 'succeeded' })

    await waitFor(() => expect(hook.result.current.items).toMatchObject([{ kind: 'answer', text: '旧的那轮' }]))
    expect(test.closes[0]).toHaveBeenCalledOnce()
    expect(test.options).toHaveLength(1)
  })

  it('reports a failed one-shot read', async () => {
    const test = harness()
    const failure = new Error('读不到历史')
    fetchRunReplayMock.mockRejectedValue(failure)

    const hook = renderHook(() => useRunEvents('run-a', 'succeeded'), { wrapper: test.wrapper })

    await waitFor(() => expect(hook.result.current.connectionError).toBe(failure))
    expect(test.options).toHaveLength(0)
  })

  // 一次性读取不会重连，「正在等待传输层重连」在这条路径上是句假话
  it('never claims a one-shot read is waiting to reconnect', async () => {
    const test = harness()
    fetchRunReplayMock.mockRejectedValue(new Error('读不到历史'))

    const hook = renderHook(() => useRunEvents('run-a', 'succeeded'), { wrapper: test.wrapper })

    await waitFor(() => expect(hook.result.current.connectionError).not.toBeNull())
    expect(hook.result.current.connectionRetryable).toBe(false)
  })

  // run 已经结束、回答已经完整，界面上却挂着一条红色的「正在等待重连」——
  // 它不会再重连了。而断线期间漏掉的那段内容也确实可能缺，所以是补齐而不是光把话删掉
  it('fills the gap and clears the error once a broken run reaches a terminal state', async () => {
    const test = harness()
    const hook = renderHook(
      ({ status }: { status: RunStatus }) => useRunEvents('run-a', status),
      { initialProps: { status: 'running' as RunStatus }, wrapper: test.wrapper },
    )
    act(() => test.options[0].onMessage({ eventName: 'token', lastEventId: '100-0', data: token('run-a', '断线前') }))
    act(() => test.options[0].onError?.(new Error('断线')))
    expect(hook.result.current.connectionError).not.toBeNull()

    fetchRunReplayMock.mockResolvedValue([replayedToken('run-a', '断线前也断线后')])
    hook.rerender({ status: 'succeeded' })

    await waitFor(() => expect(hook.result.current.connectionError).toBeNull())
    expect(fetchRunReplayMock).toHaveBeenCalledWith('run-a')
    expect(hook.result.current.items).toMatchObject([{ kind: 'answer', text: '断线前也断线后' }])
  })

  // 终态是从 runs 列表同步来的，事件流那边可能一条都没收到（比如一直被 429 拒）。
  // 不关掉它的话：流继续重连报错 → 红字亮；补齐逻辑清掉错误 → 红字灭 —— 一闪一闪
  it('closes the stream once the run is known to be finished', () => {
    const test = harness()
    const hook = renderHook(
      ({ status }: { status: RunStatus }) => useRunEvents('run-a', status),
      { initialProps: { status: 'running' as RunStatus }, wrapper: test.wrapper },
    )
    expect(test.options).toHaveLength(1)

    hook.rerender({ status: 'succeeded' })

    expect(test.closes[0]).toHaveBeenCalled()
    expect(test.options).toHaveLength(1)
  })

  it('keeps streaming while the run is still waiting for approval', () => {
    const test = harness()
    const hook = renderHook(
      ({ status }: { status: RunStatus }) => useRunEvents('run-a', status),
      { initialProps: { status: 'running' as RunStatus }, wrapper: test.wrapper },
    )

    hook.rerender({ status: 'waiting_approval' })

    expect(test.closes[0]).not.toHaveBeenCalled()
  })

  it('leaves a healthy run alone when it finishes', () => {
    const test = harness()
    const hook = renderHook(
      ({ status }: { status: RunStatus }) => useRunEvents('run-a', status),
      { initialProps: { status: 'running' as RunStatus }, wrapper: test.wrapper },
    )
    act(() => test.options[0].onMessage({ eventName: 'token', lastEventId: '100-0', data: token('run-a', '一切正常') }))

    hook.rerender({ status: 'succeeded' })

    expect(fetchRunReplayMock).not.toHaveBeenCalled()
    expect(hook.result.current.items).toMatchObject([{ kind: 'answer', text: '一切正常' }])
  })

  it('retains rendered output while one transport connection recovers in place', () => {
    const test = harness()
    const hook = renderHook(() => useRunEvents('run-a', 'running'), { wrapper: test.wrapper })
    act(() => test.options[0].onMessage({ eventName: 'token', lastEventId: '100-0', data: token('run-a', '断线前') }))

    act(() => test.options[0].onError?.(new Error('断线')))
    expect(hook.result.current.items).toMatchObject([{ kind: 'answer', text: '断线前' }])

    act(() => {
      test.options[0].onOpen?.()
      test.options[0].onMessage({ eventName: 'token', lastEventId: '101-0', data: token('run-a', '断线后') })
    })

    expect(test.options).toHaveLength(1)
    expect(hook.result.current.connectionError).toBeNull()
    expect(hook.result.current.items).toMatchObject([{ kind: 'answer', text: '断线前断线后' }])
  })

  it('keeps the connection at interrupt and closes it at a terminal event', () => {
    const test = harness()
    const onTerminal = vi.fn()
    const hook = renderHook(() => useRunEvents('run-a', 'running', { onTerminal }), { wrapper: test.wrapper })
    act(() => test.options[0].onMessage({
      eventName: 'interrupt',
      lastEventId: '101-0',
      data: JSON.stringify({ type: 'interrupt', ts: 1, run_id: 'run-a', path: [], data: { actions: [] } }),
    }))
    expect(test.closes[0]).not.toHaveBeenCalled()
    expect(hook.result.current.status).toBe('waiting_approval')

    act(() => test.options[0].onMessage({
      eventName: 'run.finished',
      lastEventId: '102-0',
      data: JSON.stringify({ type: 'run.finished', ts: 2, run_id: 'run-a', path: [], data: { status: 'succeeded', tokens: { input_cache_read: 0, input_uncached: 0, output: 1 } } }),
    }))
    expect(test.closes[0]).toHaveBeenCalledOnce()
    expect(hook.result.current.status).toBe('succeeded')
    expect(onTerminal).toHaveBeenCalledWith('succeeded')
  })

  it.each([
    ['queued', 'queued', false],
    ['waiting_approval', 'waiting_approval', true],
  ] as const)('reconciles a replayed interrupt with authoritative %s status', async (resolved, expected, showsApproval) => {
    const test = harness()
    const resolveInterruptStatus = vi.fn<() => Promise<RunStatus>>().mockResolvedValue(resolved)
    const hook = renderHook(
      () => useRunEvents('run-a', 'queued', { resolveInterruptStatus }),
      { wrapper: test.wrapper },
    )

    await act(async () => {
      test.options[0].onMessage({
        eventName: 'run.started',
        lastEventId: '100-0',
        data: JSON.stringify({ type: 'run.started', ts: 1, run_id: 'run-a', path: [], data: { thread_id: 'thread-a', resumed: false } }),
      })
      test.options[0].onMessage({
        eventName: 'interrupt',
        lastEventId: '101-0',
        data: JSON.stringify({ type: 'interrupt', ts: 2, run_id: 'run-a', path: [], data: { actions: [
          { index: 0, tool_name: 'delete', args: { path: 'a' }, allowed_decisions: ['approve'] },
        ] } }),
      })
      await Promise.resolve()
    })

    expect(resolveInterruptStatus).toHaveBeenCalledOnce()
    expect(hook.result.current.status).toBe(expected)
    expect(Boolean(hook.result.current.pendingActions)).toBe(showsApproval)
  })

  it('ignores an interrupt status result after a newer event advances the cursor', async () => {
    const test = harness()
    let resolveStatus: ((status: RunStatus) => void) | undefined
    const resolveInterruptStatus = () => new Promise<RunStatus>(resolve => { resolveStatus = resolve })
    const hook = renderHook(
      () => useRunEvents('run-a', 'running', { resolveInterruptStatus }),
      { wrapper: test.wrapper },
    )

    act(() => {
      test.options[0].onMessage({
        eventName: 'interrupt',
        lastEventId: '101-0',
        data: JSON.stringify({ type: 'interrupt', ts: 1, run_id: 'run-a', path: [], data: { actions: [] } }),
      })
      test.options[0].onMessage({ eventName: 'token', lastEventId: '102-0', data: token('run-a', '继续') })
    })
    await act(async () => {
      resolveStatus?.('waiting_approval')
      await Promise.resolve()
    })

    expect(hook.result.current.status).toBe('running')
    expect(hook.result.current.pendingActions).toBeNull()
    expect(hook.result.current.items).toMatchObject([{ kind: 'answer', text: '继续' }])
  })

  it('ignores a pending interrupt status result after unmount', async () => {
    const test = harness()
    let resolveStatus: ((status: RunStatus) => void) | undefined
    const resolveInterruptStatus = () => new Promise<RunStatus>(resolve => { resolveStatus = resolve })
    const hook = renderHook(
      () => useRunEvents('run-a', 'running', { resolveInterruptStatus }),
      { wrapper: test.wrapper },
    )

    act(() => test.options[0].onMessage({
      eventName: 'interrupt',
      lastEventId: '101-0',
      data: JSON.stringify({ type: 'interrupt', ts: 1, run_id: 'run-a', path: [], data: { actions: [] } }),
    }))
    hook.unmount()
    await act(async () => {
      resolveStatus?.('waiting_approval')
      await Promise.resolve()
    })

    expect(test.closes[0]).toHaveBeenCalledOnce()
  })

  it('does not read anything until an on-demand historical replay is enabled', () => {
    const test = harness()
    const hook = renderHook(
      ({ enabled }) => useRunEvents('run-a', 'succeeded', { enabled }),
      { initialProps: { enabled: false }, wrapper: test.wrapper },
    )
    expect(fetchRunReplayMock).not.toHaveBeenCalled()

    hook.rerender({ enabled: true })

    expect(fetchRunReplayMock).toHaveBeenCalledWith('run-a')
    expect(test.options).toHaveLength(0)
  })

  it('does not clear accumulated output on a resumed run.started event', () => {
    const test = harness()
    const hook = renderHook(() => useRunEvents('run-a', 'running'), { wrapper: test.wrapper })
    act(() => {
      test.options[0].onMessage({ eventName: 'token', lastEventId: '100-0', data: token('run-a', '已有内容') })
      test.options[0].onMessage({
        eventName: 'run.started',
        lastEventId: '101-0',
        data: JSON.stringify({ type: 'run.started', ts: 2, run_id: 'run-a', path: [], data: { thread_id: 'thread-a', resumed: true } }),
      })
    })
    expect(hook.result.current.items).toMatchObject([{ kind: 'answer', text: '已有内容' }])
    expect(hook.result.current.status).toBe('running')
  })

  it('surfaces transport errors, clears them on open, and marks approval submission', () => {
    const test = harness()
    const hook = renderHook(() => useRunEvents('run-a', 'running'), { wrapper: test.wrapper })
    act(() => test.options[0].onError?.(new Error('断线')))
    expect(hook.result.current.connectionError).toEqual(new Error('断线'))
    expect(hook.result.current.connectionRetryable).toBe(true)

    act(() => test.options[0].onError?.({ retryable: false }))
    expect(hook.result.current.connectionRetryable).toBe(false)

    act(() => test.options[0].onOpen?.())
    expect(hook.result.current.connectionError).toBeNull()
    expect(hook.result.current.connectionRetryable).toBe(false)

    act(() => test.options[0].onMessage({
      eventName: 'interrupt',
      lastEventId: '101-0',
      data: JSON.stringify({ type: 'interrupt', ts: 1, run_id: 'run-a', path: [], data: { actions: [
        { index: 0, tool_name: 'delete', args: { path: 'a' }, allowed_decisions: ['approve'] },
      ] } }),
    }))
    act(() => hook.result.current.markApprovalSubmitted())
    expect(hook.result.current.status).toBe('queued')
    expect(hook.result.current.pendingActions).toBeNull()
  })

  it.each([
    ['run.failed', 'failed', { code: 'INTERNAL', message: '失败', retryable: false }],
    ['run.cancelled', 'cancelled', { tokens: { input_cache_read: 0, input_uncached: 0, output: 0 } }],
  ] as const)('closes and reports %s', (eventName, status, data) => {
    const test = harness()
    const onTerminal = vi.fn()
    renderHook(() => useRunEvents('run-a', 'running', { onTerminal }), { wrapper: test.wrapper })

    act(() => test.options[0].onMessage({
      eventName,
      lastEventId: '200-0',
      data: JSON.stringify({ type: eventName, ts: 1, run_id: 'run-a', path: [], data }),
    }))

    expect(test.closes[0]).toHaveBeenCalledOnce()
    expect(onTerminal).toHaveBeenCalledWith(status)
  })
})
