import {
  EventStreamContentType,
  fetchEventSource,
  type EventSourceMessage,
} from '@microsoft/fetch-event-source'
import type { RunEventTransport } from './events'
import { notifyUnauthorized } from './request'

class RunEventTransportError extends Error {
  readonly retryable: boolean
  readonly status: number

  constructor(message: string, status: number, retryable: boolean) {
    super(message)
    this.name = 'RunEventTransportError'
    this.status = status
    this.retryable = retryable
  }
}

function mediaType(response: Response): string {
  return (response.headers.get('content-type') ?? '').split(';', 1)[0].trim().toLowerCase()
}

function responseError(response: Response): RunEventTransportError {
  if (response.status === 401) {
    notifyUnauthorized()
    return new RunEventTransportError('登录状态已失效', 401, false)
  }
  if (response.status === 403) {
    return new RunEventTransportError('无权订阅该运行的事件', 403, false)
  }
  const retryable = response.status === 408
    || response.status === 425
    || response.status === 429
    || response.status >= 500
  return new RunEventTransportError(
    `事件流请求失败（${response.status}）`,
    response.status,
    retryable,
  )
}

function isAllowedEvent(eventNames: ReadonlySet<string>, message: EventSourceMessage): boolean {
  return eventNames.has(message.event)
}

export const runEventTransport: RunEventTransport = {
  connect(options) {
    const controller = new AbortController()
    const eventNames = new Set<string>(options.eventNames)
    let cursor = options.cursor
    let sawEventFrame = false

    const headers: Record<string, string> = { accept: EventStreamContentType }
    if (cursor) headers['last-event-id'] = cursor

    // fetch-event-source mutates its private header object as soon as it parses an
    // id line. Override that value at request time so reconnects resume only after
    // the latest complete SSE frame observed by onmessage.
    const fetchWithCompletedCursor: typeof fetch = (input, init) => {
      const requestHeaders = new Headers(init?.headers)
      if (cursor) requestHeaders.set('last-event-id', cursor)
      else requestHeaders.delete('last-event-id')
      return globalThis.fetch(input, { ...init, headers: requestHeaders })
    }

    void fetchEventSource(options.url, {
      credentials: 'include',
      fetch: fetchWithCompletedCursor,
      headers,
      openWhenHidden: true,
      signal: controller.signal,
      async onopen(response) {
        if (response.status !== 200) throw responseError(response)
        if (mediaType(response) !== EventStreamContentType) {
          throw new RunEventTransportError(
            `事件流响应类型错误（${response.headers.get('content-type') ?? '缺失'}）`,
            response.status,
            false,
          )
        }
        sawEventFrame = false
        options.onOpen?.()
      },
      onmessage(message) {
        if (message.id || message.event || message.data) sawEventFrame = true
        // onmessage is the complete-frame boundary. Advance before filtering so
        // future/unknown event types are not replayed forever after a reconnect.
        if (message.id) cursor = message.id
        if (!isAllowedEvent(eventNames, message)) return
        options.onMessage({
          eventName: message.event,
          data: message.data,
          lastEventId: message.id || cursor || '',
        })
      },
      onclose() {
        if (options.allowEmptyClose && !sawEventFrame) return
        throw new RunEventTransportError('事件流意外关闭', 0, true)
      },
      onerror(error) {
        options.onError?.(error)
        if (error instanceof RunEventTransportError && !error.retryable) throw error
      },
    }).catch(() => undefined)

    return {
      close() {
        controller.abort()
      },
    }
  },
}
