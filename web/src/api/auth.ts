import { fetchApi, setTokens } from './client'
import type { AuthResponse, User } from '@/types'

export async function register(
  email: string,
  username: string,
  password: string,
  displayName?: string,
): Promise<AuthResponse> {
  const data = await fetchApi<AuthResponse>('/api/auth/register', {
    method: 'POST',
    body: JSON.stringify({ email, username, password, display_name: displayName }),
  })
  setTokens(data.tokens.access_token, data.tokens.refresh_token)
  return data
}

export async function login(
  email: string,
  password: string,
): Promise<AuthResponse> {
  const data = await fetchApi<AuthResponse>('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  })
  setTokens(data.tokens.access_token, data.tokens.refresh_token)
  return data
}

export async function getMe(): Promise<{ user: User }> {
  return fetchApi<{ user: User }>('/api/auth/me')
}

export async function updateProfile(data: {
  display_name?: string
}): Promise<{ user: User }> {
  return fetchApi<{ user: User }>('/api/auth/me', {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export async function changePassword(currentPassword: string, newPassword: string): Promise<{ message: string }> {
  return fetchApi<{ message: string }>('/api/auth/me/password', {
    method: 'POST',
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  })
}
