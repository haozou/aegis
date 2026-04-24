import { AuthLayout } from '@/components/layout/auth-layout'
import { LoginForm } from '@/components/auth/login-form'

export function LoginPage() {
  return (
    <AuthLayout>
      <LoginForm />
    </AuthLayout>
  )
}
