const ACCESS_KEY = 'pd.access'
const REFRESH_KEY = 'pd.refresh'

export type AuthTokens = {
  access: string
  refresh: string
}

export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_KEY)
}

export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_KEY)
}

export function setTokens(tokens: AuthTokens): void {
  localStorage.setItem(ACCESS_KEY, tokens.access)
  localStorage.setItem(REFRESH_KEY, tokens.refresh)
}

export function clearTokens(): void {
  localStorage.removeItem(ACCESS_KEY)
  localStorage.removeItem(REFRESH_KEY)
}

export function isAuthenticated(): boolean {
  return Boolean(getAccessToken())
}
