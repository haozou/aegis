import { create } from 'zustand'
import { clearTokens, getAccessToken } from '@/api/client'
import { getMe } from '@/api/auth'
import type { User } from '@/types'

interface AuthState {
  user: User | null
  isLoading: boolean
  isAuthenticated: boolean

  initialize: () => Promise<void>
  setUser: (user: User) => void
  updateUser: (user: User) => void
  logout: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  isLoading: true,
  isAuthenticated: false,

  initialize: async () => {
    const token = getAccessToken()
    if (!token) {
      set({ isLoading: false, isAuthenticated: false })
      return
    }

    try {
      const { user } = await getMe()
      set({ user, isLoading: false, isAuthenticated: true })
    } catch {
      clearTokens()
      set({ user: null, isLoading: false, isAuthenticated: false })
    }
  },

  setUser: (user: User) => {
    set({ user, isAuthenticated: true, isLoading: false })
  },

  updateUser: (user: User) => {
    set({ user })
  },

  logout: () => {
    clearTokens()
    set({ user: null, isAuthenticated: false })
  },
}))
