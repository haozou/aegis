import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { UserMenu } from '@/components/user-menu'
import { listAgents, createAgent, deleteAgent, cloneAgent, getAgentUsage, type AgentUsage } from '@/api/agents'
import { listModels } from '@/api/models'
import type { Agent } from '@/types'

export function DashboardPage() {
  const [agents, setAgents] = useState<Agent[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [newName, setNewName] = useState('')
  const [newPrompt, setNewPrompt] = useState('')
  const [newModel, setNewModel] = useState('claude-sonnet-4-5')
  const [creating, setCreating] = useState(false)
  const [usageMap, setUsageMap] = useState<Record<string, AgentUsage>>({})
  const [availableModels, setAvailableModels] = useState<string[]>([])
  const navigate = useNavigate()

  async function loadAgents() {
    try {
      const { agents: list } = await listAgents()
      setAgents(list)
      // Load usage stats for all agents in parallel
      const usageResults = await Promise.allSettled(
        list.map(a => getAgentUsage(a.id))
      )
      const map: Record<string, AgentUsage> = {}
      usageResults.forEach((r, i) => {
        if (r.status === 'fulfilled') map[list[i].id] = r.value
      })
      setUsageMap(map)
    } catch {
      // ignore
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadAgents()
  }, [])

  useEffect(() => {
    listModels()
      .then(({ models, default: def }) => {
        setAvailableModels(models)
        setNewModel(def)
      })
      .catch(() => {})
  }, [])

  async function handleCreate() {
    if (!newName.trim()) return
    setCreating(true)
    try {
      const { agent } = await createAgent({
        name: newName.trim(),
        system_prompt: newPrompt.trim(),
        description: newPrompt.trim().slice(0, 100),
        model: newModel,
      })
      navigate(`/agents/${agent.id}/settings`)
    } catch {
      // ignore
    } finally {
      setCreating(false)
    }
  }

  async function handleDelete(e: React.MouseEvent, id: string) {
    e.stopPropagation()
    if (!confirm('Delete this agent?')) return
    try {
      await deleteAgent(id)
      setAgents((prev) => prev.filter((a) => a.id !== id))
    } catch {
      // ignore
    }
  }

  async function handleClone(e: React.MouseEvent, id: string) {
    e.stopPropagation()
    try {
      const { agent } = await cloneAgent(id)
      setAgents((prev) => [agent, ...prev])
    } catch {
      // ignore
    }
  }

  function formatTokens(n: number): string {
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
    if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
    return String(n)
  }

  const statusColors: Record<string, string> = {
    active: 'bg-emerald-500',
    draft: 'bg-yellow-500',
    paused: 'bg-orange-500',
    archived: 'bg-zinc-500',
  }

  return (
    <div className="min-h-svh bg-background">
      {/* Header */}
      <header className="border-b border-border bg-card">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3 sm:px-6 sm:py-4">
          <div className="flex items-center gap-3">
            <button
              onClick={() => navigate('/')}
              className="rounded-lg p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
              title="Back to chat"
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <path d="M10 3L5 8l5 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </button>
            <h1 className="text-lg font-bold text-foreground sm:text-xl">Dashboard</h1>
          </div>
          <UserMenu dropdownPosition="below" />
        </div>
      </header>

      {/* Content */}
      <main className="mx-auto max-w-6xl px-4 py-6 sm:px-6 sm:py-8">
        {/* Summary Stats */}
        {!loading && agents.length > 0 && (
          <div className="mb-8 grid grid-cols-2 gap-3 sm:grid-cols-4 sm:gap-4">
            <div className="rounded-lg border border-border bg-card p-3 sm:p-4">
              <div className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">Agents</div>
              <div className="mt-1 text-xl font-bold text-foreground sm:text-2xl">{agents.length}</div>
            </div>
            <div className="rounded-lg border border-border bg-card p-3 sm:p-4">
              <div className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">Total Chats</div>
              <div className="mt-1 text-xl font-bold text-foreground sm:text-2xl">
                {Object.values(usageMap).reduce((sum, u) => sum + u.conversation_count, 0)}
              </div>
            </div>
            <div className="rounded-lg border border-border bg-card p-3 sm:p-4">
              <div className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">Total Tokens</div>
              <div className="mt-1 text-xl font-bold text-foreground sm:text-2xl">
                {formatTokens(Object.values(usageMap).reduce((sum, u) => sum + u.total_tokens, 0))}
              </div>
            </div>
            <div className="rounded-lg border border-border bg-card p-3 sm:p-4">
              <div className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">Last 7 Days</div>
              <div className="mt-1 text-xl font-bold text-foreground sm:text-2xl">
                {formatTokens(Object.values(usageMap).reduce((sum, u) => sum + u.recent_tokens_7d, 0))}
              </div>
            </div>
          </div>
        )}

        <div className="mb-6 flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-semibold text-foreground">Your Agents</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Create and manage AI agents that run 24/7
            </p>
          </div>
          <Button onClick={() => setShowCreate(true)}>
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" className="mr-2">
              <path d="M8 3v10M3 8h10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
            New Agent
          </Button>
        </div>

        {/* Create Agent Dialog */}
        {showCreate && (
          <Card className="mb-8 border-primary/30 bg-card">
            <CardHeader>
              <CardTitle className="text-lg">Create New Agent</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="agent-name">Name</Label>
                <Input
                  id="agent-name"
                  placeholder="My Assistant"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="agent-prompt">System Prompt</Label>
                <textarea
                  id="agent-prompt"
                  placeholder="You are a helpful assistant that..."
                  value={newPrompt}
                  onChange={(e) => setNewPrompt(e.target.value)}
                  rows={3}
                  className="flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="agent-model">Model</Label>
                <select
                  id="agent-model"
                  value={newModel}
                  onChange={(e) => setNewModel(e.target.value)}
                  className="flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                >
                  {availableModels.length > 0 ? (
                    availableModels.map(m => (
                      <option key={m} value={m}>{m}</option>
                    ))
                  ) : (
                    <>
                      <option value="claude-sonnet-4-5">claude-sonnet-4-5</option>
                      <option value="claude-opus-4-5">claude-opus-4-5</option>
                      <option value="claude-haiku-4-5">claude-haiku-4-5</option>
                      <option value="gpt-4.1">gpt-4.1</option>
                    </>
                  )}
                </select>
              </div>
              <div className="flex gap-2">
                <Button onClick={handleCreate} disabled={creating || !newName.trim()}>
                  {creating ? 'Creating...' : 'Create Agent'}
                </Button>
                <Button variant="outline" onClick={() => setShowCreate(false)}>
                  Cancel
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Agent Grid */}
        {loading ? (
          <div className="py-12 text-center text-muted-foreground">Loading agents...</div>
        ) : agents.length === 0 ? (
          <div className="py-24 text-center">
            <div className="text-6xl mb-4">&#129302;</div>
            <h3 className="text-lg font-medium text-foreground">No agents yet</h3>
            <p className="mt-2 text-sm text-muted-foreground">
              Create your first agent to get started
            </p>
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {agents.map((agent) => (
              <Card
                key={agent.id}
                className={`cursor-pointer border-border bg-card transition-all duration-200 hover:border-primary/50 hover:-translate-y-0.5 hover:shadow-lg ${agent.status === 'active' ? 'agent-active-glow' : ''}`}
                onClick={() => navigate(`/agents/${agent.id}/settings`)}
              >
                <CardContent className="p-5">
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-3">
                      <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-lg">
                        &#129302;
                      </div>
                      <div>
                        <h3 className="font-medium text-foreground">{agent.name}</h3>
                        <div className="flex items-center gap-2 mt-1">
                          <span className={`inline-block h-2 w-2 rounded-full ${statusColors[agent.status] || 'bg-zinc-500'}`} />
                          <span className="text-xs text-muted-foreground capitalize">
                            {agent.status}
                          </span>
                        </div>
                      </div>
                    </div>
                    <div className="flex gap-1">
                      <button
                        onClick={(e) => { e.stopPropagation(); navigate(`/agents/${agent.id}/settings`) }}
                        className="rounded p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                        title="Settings"
                      >
                        <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                          <circle cx="8" cy="8" r="2" stroke="currentColor" strokeWidth="1.3"/>
                          <path d="M8 1v2M8 13v2M1 8h2M13 8h2M3.05 3.05l1.41 1.41M11.54 11.54l1.41 1.41M3.05 12.95l1.41-1.41M11.54 4.46l1.41-1.41" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
                        </svg>
                      </button>
                      <button
                        onClick={(e) => handleClone(e, agent.id)}
                        className="rounded p-1 text-muted-foreground transition-colors hover:bg-primary/20 hover:text-primary"
                        title="Clone"
                      >
                        <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                          <rect x="4" y="4" width="8" height="8" rx="1.5" stroke="currentColor" strokeWidth="1.3" />
                          <path d="M10 4V3a1.5 1.5 0 00-1.5-1.5H3A1.5 1.5 0 001.5 3v5.5A1.5 1.5 0 003 10h1" stroke="currentColor" strokeWidth="1.3" />
                        </svg>
                      </button>
                      <button
                        onClick={(e) => handleDelete(e, agent.id)}
                        className="rounded p-1 text-muted-foreground transition-colors hover:bg-destructive/20 hover:text-destructive"
                        title="Delete"
                      >
                        <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                          <path d="M3 3l8 8M11 3l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                        </svg>
                      </button>
                    </div>
                  </div>
                  {agent.description && (
                    <p className="mt-3 text-sm text-muted-foreground line-clamp-2">
                      {agent.description}
                    </p>
                  )}
                  <div className="mt-3 flex items-center gap-3 text-xs text-muted-foreground">
                    <span>{agent.model}</span>
                    <span>&middot;</span>
                    <span>{new Date(agent.updated_at).toLocaleDateString()}</span>
                  </div>
                  {usageMap[agent.id] && (
                    <div className="mt-2 flex items-center gap-3 text-[10px] text-muted-foreground/70">
                      <span title="Total tokens used">{formatTokens(usageMap[agent.id].total_tokens)} tokens</span>
                      <span>&middot;</span>
                      <span title="Total conversations">{usageMap[agent.id].conversation_count} chats</span>
                      {usageMap[agent.id].recent_tokens_7d > 0 && (
                        <>
                          <span>&middot;</span>
                          <span title="Last 7 days">{formatTokens(usageMap[agent.id].recent_tokens_7d)} (7d)</span>
                        </>
                      )}
                    </div>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </main>
    </div>
  )
}
