import { afterEach, describe, expect, it, vi } from 'vitest'
import { RUN_EVENT_NAMES } from './events'
import { runEventTransport } from './runEventTransport'

const encoder = new TextEncoder()

function eventStream(body: ReadableStream<Uint8Array>): Response {
  return new Response(body, {
    status: 200,
    headers: { 'content-type': 'text/event-stream; charset=utf-8' },
  })
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('runEventTransport with the real fetch-event-source library', () => {
  it('retries after the latest complete frame rather than an incomplete id line', async () => {
    const requests: RequestInit[] = []
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      requests.push(init ?? {})
      if (requests.length === 1) {
        let pulled = false
        return eventStream(new ReadableStream<Uint8Array>({
          pull(controller) {
            if (!pulled) {
              pulled = true
              controller.enqueue(encoder.encode([
                'retry: 0',
                'id: 100-0',
                'event: token',
                'data: {"complete":true}',
                '',
                'id: 101-0',
                'event: token',
                'data: {"complete":false}',
                '',
              ].join('\n')))
              return
            }
            controller.error(new Error('流在不完整帧中断开'))
          },
        }))
      }

      let streamController: ReadableStreamDefaultController<Uint8Array> | undefined
      const body = new ReadableStream<Uint8Array>({
        start(controller) {
          streamController = controller
        },
      })
      init?.signal?.addEventListener('abort', () => {
        streamController?.error(new DOMException('连接已关闭', 'AbortError'))
      }, { once: true })
      return eventStream(body)
    })
    vi.stubGlobal('fetch', fetchMock)
    const onMessage = vi.fn()

    const connection = runEventTransport.connect({
      url: '/api/runs/run-1/events',
      eventNames: RUN_EVENT_NAMES,
      onMessage,
    })

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    expect(onMessage).toHaveBeenCalledOnce()
    expect(onMessage).toHaveBeenCalledWith({
      eventName: 'token',
      data: '{"complete":true}',
      lastEventId: '100-0',
    })
    expect(new Headers(requests[1].headers).get('last-event-id')).toBe('100-0')
    expect(requests[1].credentials).toBe('include')

    connection.close()
  })

  it('retries a cleanly truncated prefix and accepts the next empty terminal attempt', async () => {
    const requests: RequestInit[] = []
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      requests.push(init ?? {})
      return eventStream(new ReadableStream<Uint8Array>({
        start(controller) {
          if (requests.length === 1) {
            controller.enqueue(encoder.encode([
              'retry: 0',
              'id: 200-0',
              'event: token',
              'data: {"prefix":true}',
              '',
              '',
            ].join('\n')))
          }
          controller.close()
        },
      }))
    })
    vi.stubGlobal('fetch', fetchMock)
    const onError = vi.fn()
    const onMessage = vi.fn()

    const connection = runEventTransport.connect({
      url: '/api/runs/run-2/events',
      eventNames: RUN_EVENT_NAMES,
      allowEmptyClose: true,
      onError,
      onMessage,
    })

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    await new Promise(resolve => window.setTimeout(resolve, 20))
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(onError).toHaveBeenCalledOnce()
    expect(onMessage).toHaveBeenCalledOnce()
    expect(new Headers(requests[1].headers).get('last-event-id')).toBe('200-0')

    connection.close()
  })
})
