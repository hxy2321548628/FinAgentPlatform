import { act, renderHook } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { RunEventTransportProvider } from '../api/RunEventTransportContext'
import type { RunEventConnectionOptions, RunEventTransport } from '../api/events'
import type { RunStatus } from '../api/types'
import { useRunEvents } from './useRunEvents'

function token(runId: string, text: string) {
  return JSON.stringify({ type: 'token', ts: 1, run_id: runId, path: [], data: { text } })
}

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

  it('starts a full replay with empty state and no cursor after a page remount', () => {
    const test = harness()
    const first = renderHook(() => useRunEvents('run-a', 'succeeded'), { wrapper: test.wrapper })
    act(() => test.options[0].onMessage({ eventName: 'token', lastEventId: '100-0', data: token('run-a', '旧页面') }))
    expect(first.result.current.items).toMatchObject([{ kind: 'answer', text: '旧页面' }])

    first.unmount()
    const remounted = renderHook(() => useRunEvents('run-a', 'succeeded'), { wrapper: test.wrapper })

    expect(test.closes[0]).toHaveBeenCalledOnce()
    expect(test.options[1]).toMatchObject({
      url: '/api/runs/run-a/events', cursor: undefined, allowEmptyClose: true,
    })
    expect(remounted.result.current.items).toEqual([])
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

  it('does not connect until an on-demand historical replay is enabled', () => {
    const test = harness()
    const hook = renderHook(
      ({ enabled }) => useRunEvents('run-a', 'succeeded', { enabled }),
      { initialProps: { enabled: false }, wrapper: test.wrapper },
    )
    expect(test.options).toHaveLength(0)

    hook.rerender({ enabled: true })

    expect(test.options).toHaveLength(1)
    expect(test.options[0].url).toBe('/api/runs/run-a/events')
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
