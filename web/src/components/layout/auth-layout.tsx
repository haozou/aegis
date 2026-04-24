import type { ReactNode } from 'react'

export function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-svh items-center justify-center bg-background p-4">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <h1 className="text-3xl font-bold tracking-tight text-foreground">
            Aegis
          </h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Agent Factory Platform
          </p>
        </div>
        {children}
      </div>
    </div>
  )
}
