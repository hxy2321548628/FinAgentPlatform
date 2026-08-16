import type { FetchEventSourceInit } from '@microsoft/fetch-event-source'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { RUN_EVENT_NAMES, type RunEventConnectionOptions } from './events'
import { setUnauthorizedHandler } from './request'

const fetchEventSourceMock = vi.hoisted(() => vi.fn())

vi.mock('@microsoft/fetch-event-source', () => ({
  EventStreamContentType: 'text/event-stream',
  fetchEventSource: fetchEventSourceMock,
}))

import { runEventTransport } from './runEventTransport'

type CapturedInit = FetchEventSourceInit & Required<Pick<
  FetchEventSourceInit,
  'onopen' | 'onmessage' | 'onclose' | 'onerror' | 'fetch'
>>

function capturedInit(): CapturedInit {
  return fetchEventSourceMock.mock.lastCall?.[1] as CapturedInit
}

function connect(overrides: Partial<RunEventConnectionOptions> = {}) {
  const options: RunEventConnectionOptions = {
    url: '/api/runs/run-1/events',
    eventNames: RUN_EVENT_NAMES,
    onMessage: vi.fn(),
    onError: vi.fn(),
    onOpen: vi.fn(),
    ...overrides,
  }
  const connection = runEventTransport.connect(options)
  return { connection, options }
}

beforeEach(() => {
  fetchEventSourceMock.mockReset()
  fetchEventSourceMock.mockReturnValue(new Promise<void>(() => undefined))
})

afterEach(() => {
  vi.unstubAllGlobals()
  setUnauthorizedHandler()
})

describe('runEventTransport', () => {
  it('sends credentials, the optional initial cursor and accepts a valid SSE response', async () => {
    const { options } = connect({ cursor: '100-0' })
    const init = capturedInit()

    expect(fetchEventSourceMock).toHaveBeenCalledWith('/api/runs/run-1/events', expect.any(Object))
    expect(init.credentials).toBe('include')
    expect(init.openWhenHidden).toBe(true)
    expect(init.headers).toEqual({ accept: 'text/event-stream', 'last-event-id': '100-0' })

    await init.onopen(new Response(null, {
      status: 200,
      headers: { 'content-type': 'Text/Event-Stream; charset=utf-8' },
    }))
    expect(options.onOpen).toHaveBeenCalledOnce()
  })

  it('omits Last-Event-ID without an initial cursor and forwards all 15 named events', () => {
    const { options } = connect()
    const init = capturedInit()

    expect(init.headers).toEqual({ accept: 'text/event-stream' })
    for (const [index, eventName] of RUN_EVENT_NAMES.entries()) {
      init.onmessage({
        event: eventName,
        id: `${index + 1}-0`,
        data: JSON.stringify({ type: eventName }),
      })
    }
    init.onmessage({ event: 'unknown.event', id: '16-0', data: '{}' })

    expect(options.onMessage).toHaveBeenCalledTimes(15)
    expect(options.onMessage).toHaveBeenLastCalledWith({
      eventName: 'interrupt',
      lastEventId: '15-0',
      data: JSON.stringify({ type: 'interrupt' }),
    })
  })

  it('overrides the library retry header with the latest complete frame cursor', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    const onMessage = vi.fn()
    connect({ cursor: '100-0', onMessage })
    const init = capturedInit()

    await init.fetch('/api/runs/run-1/events', {
      headers: { 'last-event-id': '999-incomplete' },
    })
    expect(new Headers(fetchMock.mock.calls[0][1]?.headers).get('last-event-id')).toBe('100-0')

    // Unknown frames still advance the reconnect cursor after the complete-frame callback.
    init.onmessage({ event: 'future.event', id: '101-0', data: '{' })
    await init.fetch('/api/runs/run-1/events', {
      headers: { 'last-event-id': '999-incomplete' },
    })
    expect(new Headers(fetchMock.mock.calls[1][1]?.headers).get('last-event-id')).toBe('101-0')
    expect(onMessage).not.toHaveBeenCalled()

    init.onmessage({ event: 'token', id: '102-0', data: '{"text":"喵"}' })
    await init.fetch('/api/runs/run-1/events', {
      headers: { 'last-event-id': '999-incomplete' },
    })
    expect(new Headers(fetchMock.mock.calls[2][1]?.headers).get('last-event-id')).toBe('102-0')
    expect(onMessage).toHaveBeenCalledWith({
      eventName: 'token',
      lastEventId: '102-0',
      data: '{"text":"喵"}',
    })
  })

  it('aborts the active connection when closed', () => {
    const { connection } = connect()
    const signal = capturedInit().signal

    expect(signal?.aborted).toBe(false)
    connection.close()
    connection.close()
    expect(signal?.aborted).toBe(true)
  })

  it('stops retrying a 401 response and invokes the unified unauthorized handler', async () => {
    const unauthorized = vi.fn()
    const onError = vi.fn()
    setUnauthorizedHandler(unauthorized)
    connect({ onError })
    const init = capturedInit()

    const error = await init.onopen(new Response(null, { status: 401 })).catch(caught => caught)

    expect(unauthorized).toHaveBeenCalledOnce()
    expect(error).toMatchObject({ status: 401, retryable: false, message: '登录状态已失效' })
    expect(() => init.onerror(error)).toThrow(error)
    expect(onError).toHaveBeenCalledWith(error)
  })

  it('rejects a non-SSE 200 response without retrying', async () => {
    const onError = vi.fn()
    connect({ onError })
    const init = capturedInit()

    const error = await init.onopen(new Response(null, {
      status: 200,
      headers: { 'content-type': 'application/json' },
    })).catch(caught => caught)

    expect(error).toMatchObject({ status: 200, retryable: false })
    expect(() => init.onerror(error)).toThrow(error)
    expect(onError).toHaveBeenCalledWith(error)
  })

  it('allows retries for temporary HTTP failures and an unexpected stream close', async () => {
    const onError = vi.fn()
    connect({ onError })
    const init = capturedInit()

    const responseError = await init.onopen(new Response(null, { status: 503 })).catch(caught => caught)
    expect(responseError).toMatchObject({ status: 503, retryable: true })
    expect(init.onerror(responseError)).toBe(1000)

    let closeError: unknown
    try {
      init.onclose()
    } catch (caught) {
      closeError = caught
    }
    expect(closeError).toMatchObject({ status: 0, retryable: true })
    expect(init.onerror(closeError)).toBe(2000)
    expect(onError).toHaveBeenCalledTimes(2)
  })

  // 每次重连都消耗一个限流名额，而库的默认间隔是固定 1000ms —— 撞上 429 之后
  // 它每秒撞一次，60 秒滑动窗口就再也清不空，闸门自己把自己锁死。
  it('backs off exponentially so a rate-limited stream stops feeding the limiter', async () => {
    connect()
    const init = capturedInit()
    const refused = async () => init.onopen(new Response(null, { status: 429 })).catch(caught => caught)

    const delays: unknown[] = []
    for (let attempt = 0; attempt < 7; attempt += 1) {
      delays.push(init.onerror(await refused()))
    }

    expect(delays).toEqual([1000, 2000, 4000, 8000, 16000, 30000, 30000])
  })

  it('resets the backoff once a connection opens successfully', async () => {
    connect()
    const init = capturedInit()

    init.onerror(await init.onopen(new Response(null, { status: 429 })).catch(caught => caught))
    expect(init.onerror(await init.onopen(new Response(null, { status: 429 })).catch(caught => caught))).toBe(2000)

    await init.onopen(new Response(null, {
      status: 200,
      headers: { 'content-type': 'text/event-stream' },
    }))

    expect(init.onerror(await init.onopen(new Response(null, { status: 429 })).catch(caught => caught))).toBe(1000)
  })

  it('retries a non-empty clean close then accepts an empty retry attempt', async () => {
    connect({ allowEmptyClose: true })
    const init = capturedInit()
    const validResponse = () => new Response(null, {
      status: 200,
      headers: { 'content-type': 'text/event-stream' },
    })

    await init.onopen(validResponse())
    init.onmessage({ event: 'token', id: '100-0', data: '{}' })
    expect(() => init.onclose()).toThrow(expect.objectContaining({ retryable: true }))

    await init.onopen(validResponse())
    expect(init.onclose()).toBeUndefined()
  })
})
