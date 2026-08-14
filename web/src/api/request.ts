export const ERROR_CODES = [
  'UNAUTHENTICATED',
  'FORBIDDEN',
  'NOT_FOUND',
  'VALIDATION_ERROR',
  'RATE_LIMITED',
  'QUOTA_EXCEEDED',
  'CONCURRENCY_LIMIT',
  'INTERNAL',
] as const

export type ErrorCode = (typeof ERROR_CODES)[number]

interface ErrorBody {
  error: {
    code: ErrorCode
    message: string
  }
}

export class ApiError extends Error {
  readonly status: number
  readonly code: ErrorCode

  constructor(status: number, code: ErrorCode, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

export interface RequestOptions extends Omit<RequestInit, 'body'> {
  body?: BodyInit | null
  json?: unknown
  redirectOn401?: boolean
}

type UnauthorizedHandler = () => void

function defaultUnauthorizedHandler() {
  if (window.location.pathname !== '/login') window.location.assign('/login')
}

let unauthorizedHandler: UnauthorizedHandler = defaultUnauthorizedHandler

export function setUnauthorizedHandler(handler: UnauthorizedHandler = defaultUnauthorizedHandler) {
  unauthorizedHandler = handler
}

export function notifyUnauthorized() {
  unauthorizedHandler()
}

function isErrorCode(value: unknown): value is ErrorCode {
  return typeof value === 'string' && (ERROR_CODES as readonly string[]).includes(value)
}

function errorBody(value: unknown): ErrorBody | null {
  if (typeof value !== 'object' || value === null || !('error' in value)) return null
  const error = value.error
  if (typeof error !== 'object' || error === null || !('code' in error) || !('message' in error)) return null
  if (!isErrorCode(error.code) || typeof error.message !== 'string') return null
  return { error: { code: error.code, message: error.message } }
}

async function responseValue(response: Response): Promise<unknown> {
  if (response.status === 204) return undefined
  const text = await response.text()
  if (!text) return undefined
  const contentType = response.headers.get('Content-Type') ?? ''
  if (!contentType.includes('json')) return text
  try {
    return JSON.parse(text) as unknown
  } catch {
    return text
  }
}

export async function request<T>(url: string, options: RequestOptions = {}): Promise<T> {
  const { json, redirectOn401 = true, headers: suppliedHeaders, ...init } = options
  const headers = new Headers(suppliedHeaders)
  let body = options.body
  if ('json' in options) {
    headers.set('Content-Type', 'application/json')
    body = JSON.stringify(json)
  }

  let response: Response
  try {
    response = await fetch(url, {
      ...init,
      body,
      credentials: options.credentials ?? 'include',
      headers,
    })
  } catch (error) {
    throw new ApiError(0, 'INTERNAL', error instanceof Error ? error.message : '无法连接服务')
  }

  const value = await responseValue(response)
  if (response.ok) return value as T

  const platformError = errorBody(value)
  const code = platformError?.error.code ?? 'INTERNAL'
  const message = platformError?.error.message ?? `请求失败（${response.status}）`
  if (response.status === 401 && redirectOn401) notifyUnauthorized()
  throw new ApiError(response.status, code, message)
}

export function errorMessage(error: unknown, fallback = '请求失败，请稍后重试'): string {
  return error instanceof Error ? error.message : fallback
}
