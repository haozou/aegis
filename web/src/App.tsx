import { useEffect, useState } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from '@/stores/auth-store'
import { ProtectedRoute } from '@/components/layout/protected-route'
import { LoginPage } from '@/pages/login'
import { RegisterPage } from '@/pages/register'
import { DashboardPage } from '@/pages/dashboard'
import { AgentChatPage } from '@/pages/agent-chat'
import { ChatPage } from '@/pages/chat'
import { AgentSettingsPage } from '@/pages/agent-settings'
import { ChannelsPage } from '@/pages/channels'
import { SchedulesPage } from '@/pages/schedules'
import { WebhooksPage } from '@/pages/webhooks'
import { KnowledgePage } from '@/pages/knowledge'
import { OAuthCompletePage } from '@/pages/oauth-complete'
import { CommandPalette } from '@/components/command-palette'

export default function App() {
  const initialize = useAuthStore((s) => s.initialize)
  const isLoading = useAuthStore((s) => s.isLoading)
  const isAuthed = useAuthStore((s) => !!s.user)
  const [cmdkOpen, setCmdkOpen] = useState(false)

  useEffect(() => {
    initialize()
  }, [initialize])

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setCmdkOpen((o) => !o)
      } else if (e.key === 'Escape') {
        setCmdkOpen(false)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  if (isLoading) {
    return (
      <div className="flex min-h-svh items-center justify-center bg-background">
        <div className="text-muted-foreground">Loading...</div>
      </div>
    )
  }

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/oauth-complete" element={<OAuthCompletePage />} />
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <ChatPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/dashboard"
          element={
            <ProtectedRoute>
              <DashboardPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/chat"
          element={<Navigate to="/" replace />}
        />
        <Route
          path="/agents/:agentId/settings"
          element={
            <ProtectedRoute>
              <AgentSettingsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/agents/:agentId"
          element={
            <ProtectedRoute>
              <AgentChatPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/channels"
          element={
            <ProtectedRoute>
              <ChannelsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/schedules"
          element={
            <ProtectedRoute>
              <SchedulesPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/webhooks"
          element={
            <ProtectedRoute>
              <WebhooksPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/knowledge"
          element={
            <ProtectedRoute>
              <KnowledgePage />
            </ProtectedRoute>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      {isAuthed && <CommandPalette open={cmdkOpen} onClose={() => setCmdkOpen(false)} />}
    </BrowserRouter>
  )
}
