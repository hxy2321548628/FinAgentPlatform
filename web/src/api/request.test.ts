import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, errorMessage, request, setUnauthorizedHandler } from './request'

afterEach(() => {
  vi.unstubAllGlobals()
  setUnauthorizedHandler()
})

describe('request', () => {
  it('sends JSON with the session cookie and parses the response', async () => {
    const fetch = vi.fn().mockResolvedValue(Response.json({ id: 'u1' }))
    vi.stubGlobal('fetch', fetch)

    await expect(request<{ id: string }>('/api/example', {
      method: 'POST',
      json: { name: '张老师' },
    })).resolves.toEqual({ id: 'u1' })

    expect(fetch).toHaveBeenCalledWith('/api/example', expect.objectContaining({
      method: 'POST',
      credentials: 'include',
      body: JSON.stringify({ name: '张老师' }),
    }))
    const init = fetch.mock.calls[0][1] as RequestInit
    expect(new Headers(init.headers).get('Content-Type')).toBe('application/json')
  })

  it('returns undefined for a 204 response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 204 })))
    await expect(request<void>('/api/example', { method: 'DELETE' })).resolves.toBeUndefined()
  })

  it('does not set a content type for FormData', async () => {
    const fetch = vi.fn().mockResolvedValue(Response.json({ ok: true }))
    vi.stubGlobal('fetch', fetch)
    const form = new FormData()
    form.append('file', new File(['x'], 'x.txt'))

    await request('/api/example', { method: 'POST', body: form })

    const init = fetch.mock.calls[0][1] as RequestInit
    expect(new Headers(init.headers).has('Content-Type')).toBe(false)
  })

  it('preserves the platform error code and message', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({
      error: { code: 'QUOTA_EXCEEDED', message: '今日配额已用完' },
    }, { status: 429 })))

    const error = await request('/api/example').catch((caught: unknown) => caught)
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({
      status: 429,
      code: 'QUOTA_EXCEEDED',
      message: '今日配额已用完',
    })
  })

  it('redirects on 401 by default but lets login keep its error', async () => {
    const unauthorized = vi.fn()
    setUnauthorizedHandler(unauthorized)
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({
      error: { code: 'UNAUTHENTICATED', message: '口令错误' },
    }, { status: 401 })))

    await request('/api/private').catch(() => undefined)
    await request('/api/auth/login', { redirectOn401: false }).catch(() => undefined)

    expect(unauthorized).toHaveBeenCalledTimes(1)
  })

  it('maps a malformed error response to INTERNAL', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('bad gateway', { status: 502 })))
    await expect(request('/api/example')).rejects.toMatchObject({
      status: 502,
      code: 'INTERNAL',
    })
  })

  it('maps transport failures and formats unknown UI errors', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('连接被拒绝')))
    await expect(request('/api/example')).rejects.toMatchObject({
      status: 0,
      code: 'INTERNAL',
      message: '连接被拒绝',
    })
    expect(errorMessage(new Error('可见错误'))).toBe('可见错误')
    expect(errorMessage(null, '备用错误')).toBe('备用错误')
  })
})
