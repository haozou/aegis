const TOKEN_KEY = 'aegis_access_token'
const REFRESH_KEY = 'aegis_refresh_token'

export function getAccessToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_KEY)
}

export function setTokens(access: string, refresh: string) {
  localStorage.setItem(TOKEN_KEY, access)
  localStorage.setItem(REFRESH_KEY, refresh)
}

export function clearTokens() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(REFRESH_KEY)
}

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
    this.name = 'ApiError'
  }
}

export async function fetchApi<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const token = getAccessToken()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string> || {}),
  }

  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  const response = await fetch(path, {
    ...options,
    headers,
  })

  if (response.status === 401) {
    // Try to refresh
    const refreshed = await tryRefresh()
    if (refreshed) {
      // Retry with new token
      headers['Authorization'] = `Bearer ${getAccessToken()}`
      const retryResponse = await fetch(path, { ...options, headers })
      if (!retryResponse.ok) {
        const err = await retryResponse.json().catch(() => ({ detail: 'Request failed' }))
        throw new ApiError(err.detail || 'Request failed', retryResponse.status)
      }
      return retryResponse.json() as Promise<T>
    }
    clearTokens()
    window.location.href = '/login'
    throw new ApiError('Session expired', 401)
  }

  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: 'Request failed' }))
    throw new ApiError(err.detail || 'Request failed', response.status)
  }

  if (response.status === 204) {
    return undefined as T
  }

  return response.json() as Promise<T>
}

async function tryRefresh(): Promise<boolean> {
  const refreshToken = getRefreshToken()
  if (!refreshToken) return false

  try {
    const response = await fetch('/api/auth/refresh', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${refreshToken}`,
        'Content-Type': 'application/json',
      },
    })

    if (!response.ok) return false

    const data = await response.json()
    setTokens(data.tokens.access_token, data.tokens.refresh_token)
    return true
  } catch {
    return false
  }
}
