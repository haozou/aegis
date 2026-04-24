import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { setTokens } from '@/api/client'
import { getMe } from '@/api/auth'
import { useAuthStore } from '@/stores/auth-store'

export function OAuthCompletePage() {
  const navigate = useNavigate()
  const setUser = useAuthStore((s) => s.setUser)
  const [error, setError] = useState('')

  useEffect(() => {
    async function handle() {
      // Tokens arrive in the URL hash: #access_token=...&refresh_token=...&expires_in=...
      const hash = window.location.hash.startsWith('#')
        ? window.location.hash.slice(1)
        : window.location.hash
      const params = new URLSearchParams(hash)
      const access = params.get('access_token')
      const refresh = params.get('refresh_token')

      if (!access || !refresh) {
        setError('Missing tokens in OAuth response')
        setTimeout(() => navigate('/login', { replace: true }), 2000)
        return
      }

      try {
        setTokens(access, refresh)
        const { user } = await getMe()
        setUser(user)
        // Clear hash so tokens don't linger in URL
        window.history.replaceState(null, '', '/')
        navigate('/', { replace: true })
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to complete sign-in')
        setTimeout(() => navigate('/login', { replace: true }), 2000)
      }
    }
    handle()
  }, [navigate, setUser])

  return (
    <div className="flex min-h-svh items-center justify-center bg-background">
      <div className="text-center">
        {error ? (
          <>
            <p className="text-destructive">{error}</p>
            <p className="mt-2 text-sm text-muted-foreground">Redirecting to login…</p>
          </>
        ) : (
          <>
            <div className="mx-auto h-8 w-8 animate-spin rounded-full border-2 border-primary border-t-transparent" />
            <p className="mt-4 text-sm text-muted-foreground">Signing you in…</p>
          </>
        )}
      </div>
    </div>
  )
}
