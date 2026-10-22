import { clearTokens, getAccessToken, getRefreshToken, setTokens } from './authStorage'
import { clearSessionMeta } from './session'

const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, '') || ''

export class ApiError extends Error {
  status: number
  body: unknown

  constructor(message: string, status: number, body: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.body = body
  }
}

type RequestOptions = {
  method?: string
  body?: unknown
  auth?: boolean
}

async function parseBody(res: Response): Promise<unknown> {
  const text = await res.text()
  if (!text) return null
  try {
    return JSON.parse(text) as unknown
  } catch {
    return text
  }
}

function firstFieldError(details: unknown): string | null {
  if (!details || typeof details !== 'object') return null
  for (const value of Object.values(details as Record<string, unknown>)) {
    if (Array.isArray(value) && typeof value[0] === 'string') return value[0]
    if (typeof value === 'string') return value
  }
  return null
}

function formatErrorMessage(body: unknown, fallback: string): string {
  if (!body || typeof body !== 'object') return fallback
  const record = body as Record<string, unknown>

  // Custom API envelope: { error: { code, message, details } }
  if (record.error && typeof record.error === 'object') {
    const err = record.error as Record<string, unknown>
    const fromDetails = firstFieldError(err.details)
    if (fromDetails) return fromDetails
    if (typeof err.message === 'string' && err.message !== 'Validation failed') {
      return err.message
    }
  }

  if (typeof record.detail === 'string') return record.detail
  const top = firstFieldError(record)
  if (top) return top
  return fallback
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = {
    Accept: 'application/json',
  }
  if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json'
  }
  if (options.auth) {
    const access = getAccessToken()
    if (access) headers.Authorization = `Bearer ${access}`
  }

  let res: Response
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method: options.method ?? (options.body !== undefined ? 'POST' : 'GET'),
      headers,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    })
  } catch {
    throw new ApiError(
      'Сервер недоступен. Запустите Django API (порт 8000) или проверьте прокси.',
      0,
      null,
    )
  }

  const body = await parseBody(res)
  if (!res.ok) {
    throw new ApiError(formatErrorMessage(body, `Ошибка ${res.status}`), res.status, body)
  }
  return body as T
}

export type RegisterResponse = {
  user: { id: number; email: string | null; username: string }
  access: string
  refresh: string
}

export type LoginResponse = {
  access: string
  refresh: string
}

export async function registerAccount(input: {
  email: string
  password: string
  passwordConfirm: string
}): Promise<RegisterResponse> {
  const local = input.email.split('@')[0]?.replace(/[^a-zA-Z0-9_]/g, '') || 'user'
  const username = `${local.slice(0, 20)}_${Date.now().toString(36)}`
  const data = await apiRequest<RegisterResponse>('/api/v1/register/', {
    body: {
      email: input.email,
      username,
      password: input.password,
      password_confirm: input.passwordConfirm,
    },
  })
  setTokens({ access: data.access, refresh: data.refresh })
  return data
}

export async function loginAccount(input: {
  email: string
  password: string
}): Promise<LoginResponse> {
  const data = await apiRequest<LoginResponse>('/api/v1/login/', {
    body: {
      email: input.email,
      password: input.password,
    },
  })
  setTokens({ access: data.access, refresh: data.refresh })
  return data
}

export type WebAccessPlatform = 'telegram' | 'max'

export type WebAccessClaimResponse = {
  status: 'accepted' | 'pending'
  detail: string
  platform: WebAccessPlatform | null
  platforms: WebAccessPlatform[]
  other_platforms?: WebAccessPlatform[]
  delivery_ok: boolean
  expires_in?: number
}

export async function startWebAccessClaim(input: {
  email: string
  platform?: WebAccessPlatform
}): Promise<WebAccessClaimResponse> {
  return apiRequest<WebAccessClaimResponse>('/api/v1/web-access/claim/', {
    body: {
      email: input.email,
      ...(input.platform ? { platform: input.platform } : {}),
    },
  })
}

export async function setWebAccessPassword(input: {
  token: string
  password: string
  passwordConfirm: string
}): Promise<RegisterResponse> {
  const data = await apiRequest<RegisterResponse>('/api/v1/web-access/set-password/', {
    body: {
      token: input.token,
      password: input.password,
      password_confirm: input.passwordConfirm,
    },
  })
  setTokens({ access: data.access, refresh: data.refresh })
  return data
}

export async function logoutAccount(): Promise<void> {
  const access = getAccessToken()
  const refresh = getRefreshToken()
  try {
    if (access && refresh) {
      await fetch(`${API_BASE}/api/v1/logout/`, {
        method: 'POST',
        headers: {
          Accept: 'application/json',
          'Content-Type': 'application/json',
          Authorization: `Bearer ${access}`,
        },
        body: JSON.stringify({ refresh }),
      })
    }
  } finally {
    clearTokens()
    clearSessionMeta()
  }
}

export type MeUser = {
  id: number
  email: string | null
  username: string
  first_name: string
  timezone: string
  language: string
}

export type OnboardingStatus = {
  success?: boolean
  mode?: string
  current_timezone?: string
}

export type TimezoneLookupResult = {
  success?: boolean
  timezone_data?: { timezone: string; city?: string; country?: string; utc_offset?: string }
  multiple_options?: Array<{
    timezone: string
    city?: string
    country?: string
    utc_offset?: string
  }>
  error?: string
}

export async function fetchMe(): Promise<MeUser> {
  return apiRequest<MeUser>('/api/v1/users/me/', { auth: true })
}

export async function fetchOnboardingStatus(): Promise<OnboardingStatus> {
  return apiRequest<OnboardingStatus>('/api/v1/onboarding/status/', { auth: true })
}

export async function acceptOnboardingAgreement(step: 1 | 2): Promise<void> {
  await apiRequest('/api/v1/onboarding/accept-agreement/', {
    auth: true,
    body: { step },
  })
}

export async function setOnboardingTimezone(timezone: string): Promise<void> {
  await apiRequest('/api/v1/onboarding/timezone/', {
    auth: true,
    body: { timezone },
  })
}

export async function lookupCityTimezone(cityName: string): Promise<TimezoneLookupResult> {
  return apiRequest<TimezoneLookupResult>('/api/v1/settings/timezone/lookup/', {
    auth: true,
    body: { city_name: cityName },
  })
}

export async function confirmCityTimezone(input: {
  timezone: string
  city?: string
  country?: string
}): Promise<void> {
  await apiRequest('/api/v1/settings/timezone/confirm/', {
    auth: true,
    body: input,
  })
}

export async function patchProfile(
  profileId: number,
  data: { first_name?: string; timezone?: string },
): Promise<void> {
  await apiRequest(`/api/v1/profile/${profileId}/`, {
    method: 'PATCH',
    auth: true,
    body: data,
  })
}

export async function fetchProfileId(): Promise<number> {
  const list = await apiRequest<Array<{ id: number }> | { results: Array<{ id: number }> }>(
    '/api/v1/profile/',
    { auth: true },
  )
  if (Array.isArray(list) && list[0]?.id) return list[0].id
  if (!Array.isArray(list) && list.results?.[0]?.id) return list.results[0].id
  throw new ApiError('Не удалось получить профиль', 0, list)
}

export async function patchReminders(data: {
  notifications_enabled?: boolean
}): Promise<void> {
  await apiRequest('/api/v1/reminders/', {
    method: 'PATCH',
    auth: true,
    body: data,
  })
}

/** Best-effort local city → IANA map when lookup API is unavailable. */
export function guessTimezoneFromCity(city: string): { timezone: string; utc: string } | null {
  const key = city.trim().toLowerCase()
  const map: Record<string, { timezone: string; utc: string }> = {
    москва: { timezone: 'Europe/Moscow', utc: 'UTC+3' },
    moscow: { timezone: 'Europe/Moscow', utc: 'UTC+3' },
    'санкт-петербург': { timezone: 'Europe/Moscow', utc: 'UTC+3' },
    петербург: { timezone: 'Europe/Moscow', utc: 'UTC+3' },
    spb: { timezone: 'Europe/Moscow', utc: 'UTC+3' },
    новосибирск: { timezone: 'Asia/Novosibirsk', utc: 'UTC+7' },
    екатеринбург: { timezone: 'Asia/Yekaterinburg', utc: 'UTC+5' },
    казань: { timezone: 'Europe/Moscow', utc: 'UTC+3' },
    berlin: { timezone: 'Europe/Berlin', utc: 'UTC+1' },
    берлин: { timezone: 'Europe/Berlin', utc: 'UTC+1' },
  }
  return map[key] ?? null
}

