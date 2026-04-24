import { useEffect, useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { getAgent } from '@/api/agents'
import { AgentSettingsPanel } from '@/components/agent/settings-panel'
import type { Agent } from '@/types'

export function AgentSettingsPage() {
  const { agentId } = useParams<{ agentId: string }>()
  const navigate = useNavigate()
  const [agent, setAgent] = useState<Agent | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!agentId) return
    getAgent(agentId)
      .then(({ agent: a }) => setAgent(a))
      .catch(() => navigate('/'))
      .finally(() => setLoading(false))
  }, [agentId, navigate])

  if (loading) {
    return (
      <div className="flex min-h-svh items-center justify-center bg-background">
        <div className="text-muted-foreground text-sm">Loading...</div>
      </div>
    )
  }

  if (!agent || !agentId) return null

  return (
    <div className="min-h-svh bg-background">
      {/* Header */}
      <header className="border-b border-border bg-card sticky top-0 z-10">
        <div className="mx-auto flex max-w-4xl items-center gap-3 px-4 py-3">
          {/* Back button */}
          <button
            onClick={() => navigate(-1)}
            className="flex items-center gap-1.5 rounded-lg p-1.5 text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
            title="Back"
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M10 12L6 8l4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>

          {/* Agent name + status dot */}
          <div className="flex items-center gap-2 flex-1 min-w-0">
            <span className={`h-2 w-2 shrink-0 rounded-full ${
              agent.status === 'active' ? 'bg-emerald-500' :
              agent.status === 'draft' ? 'bg-yellow-500' :
              agent.status === 'paused' ? 'bg-orange-500' : 'bg-zinc-500'
            }`} />
            <h1 className="text-base font-semibold text-foreground truncate">{agent.name}</h1>
            <span className="text-xs text-muted-foreground hidden sm:block">&mdash; Settings</span>
          </div>

          {/* Chat link */}
          <Link
            to="/chat"
            className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground hover:bg-muted transition-colors shrink-0"
          >
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
              <path d="M2 3a1 1 0 011-1h10a1 1 0 011 1v7a1 1 0 01-1 1H5l-3 3V3z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
            </svg>
            Chat
          </Link>
        </div>
      </header>

      {/* Settings panel */}
      <div className="overflow-y-auto">
        <AgentSettingsPanel agent={agent} onUpdate={setAgent} />
      </div>
    </div>
  )
}
