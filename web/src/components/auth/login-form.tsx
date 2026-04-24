import { useState, useEffect, type FormEvent, type ReactNode } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { login } from '@/api/auth'
import { useAuthStore } from '@/stores/auth-store'

interface Provider {
  id: 'google' | 'github' | 'microsoft'
  label: string
  icon: ReactNode
}

const PROVIDERS: Provider[] = [
  {
    id: 'google',
    label: 'Continue with Google',
    icon: (
      <svg width="16" height="16" viewBox="0 0 48 48" fill="none">
        <path d="M44.5 20H24v8.5h11.8C34.7 33.9 30 37 24 37c-7.2 0-13-5.8-13-13s5.8-13 13-13c3.3 0 6.3 1.2 8.6 3.2l6.4-6.4C34.9 4.3 29.7 2 24 2 11.8 2 2 11.8 2 24s9.8 22 22 22c11 0 21-8 21-22 0-1.3-.2-2.7-.5-4z" fill="#FFC107"/>
        <path d="M6.3 14.7l7 5.1C15.1 15.1 19.2 12 24 12c3.3 0 6.3 1.2 8.6 3.2l6.4-6.4C34.9 5.3 29.7 3 24 3 16 3 9.1 7.6 6.3 14.7z" fill="#FF3D00"/>
        <path d="M24 45c5.6 0 10.6-2.1 14.4-5.6l-6.6-5.6c-2 1.4-4.7 2.2-7.8 2.2-6 0-10.6-3.1-12-8l-6.9 5.3C8.1 40 15.4 45 24 45z" fill="#4CAF50"/>
        <path d="M44.5 20H24v8.5h11.8c-.6 1.8-1.8 3.4-3.3 4.6l6.6 5.6c3.6-3.3 6-8.6 6-14.7 0-1.3-.2-2.7-.6-4z" fill="#1976D2"/>
      </svg>
    ),
  },
  {
    id: 'github',
    label: 'Continue with GitHub',
    icon: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
        <path d="M12 0C5.37 0 0 5.37 0 12c0 5.3 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.725-4.042-1.61-4.042-1.61-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.085 1.838 1.236 1.838 1.236 1.07 1.833 2.807 1.303 3.492.996.107-.775.418-1.305.762-1.605-2.665-.305-5.467-1.335-5.467-5.93 0-1.31.467-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.4 3-.405 1.02.005 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 21.795 24 17.295 24 12c0-6.63-5.37-12-12-12z"/>
      </svg>
    ),
  },
  {
    id: 'microsoft',
    label: 'Continue with Microsoft',
    icon: (
      <svg width="16" height="16" viewBox="0 0 24 24">
        <rect x="1" y="1" width="10" height="10" fill="#F25022"/>
        <rect x="13" y="1" width="10" height="10" fill="#7FBA00"/>
        <rect x="1" y="13" width="10" height="10" fill="#00A4EF"/>
        <rect x="13" y="13" width="10" height="10" fill="#FFB900"/>
      </svg>
    ),
  },
]

export function LoginForm() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const setUser = useAuthStore((s) => s.setUser)
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()

  // Show OAuth error from callback redirect (?oauth_error=...)
  useEffect(() => {
    const oauthError = searchParams.get('oauth_error')
    if (oauthError) setError(`OAuth sign-in failed: ${oauthError}`)
  }, [searchParams])

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)

    try {
      const { user } = await login(email, password)
      setUser(user)
      navigate('/', { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  function handleOAuth(provider: Provider['id']) {
    window.location.href = `/api/auth/oauth/${provider}/start`
  }

  return (
    <Card className="border-border bg-card">
      <CardHeader>
        <CardTitle className="text-xl">Sign In</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {error && (
          <div className="rounded-md bg-destructive/10 p-3 text-sm text-destructive">
            {error}
          </div>
        )}
        {/* OAuth buttons */}
        <div className="space-y-2">
          {PROVIDERS.map(p => (
            <button
              key={p.id}
              type="button"
              onClick={() => handleOAuth(p.id)}
              className="flex w-full items-center justify-center gap-2.5 rounded-md border border-border bg-background px-4 py-2 text-sm font-medium text-foreground hover:bg-muted/50 transition-colors"
            >
              {p.icon}
              <span>{p.label}</span>
            </button>
          ))}
        </div>
        {/* Divider */}
        <div className="relative py-2">
          <div className="absolute inset-0 flex items-center">
            <div className="w-full border-t border-border" />
          </div>
          <div className="relative flex justify-center text-xs">
            <span className="bg-card px-2 text-muted-foreground">or with email</span>
          </div>
        </div>
      </CardContent>
      <form onSubmit={handleSubmit}>
        <CardContent className="space-y-4 pt-0">
          <div className="space-y-2">
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              type="email"
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="password">Password</Label>
            <Input
              id="password"
              type="password"
              placeholder="Your password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>
        </CardContent>
        <CardFooter className="flex flex-col gap-4">
          <Button type="submit" className="w-full" disabled={loading}>
            {loading ? 'Signing in...' : 'Sign In'}
          </Button>
          <p className="text-sm text-muted-foreground">
            Don't have an account?{' '}
            <Link to="/register" className="text-primary hover:underline">
              Sign up
            </Link>
          </p>
        </CardFooter>
      </form>
    </Card>
  )
}
