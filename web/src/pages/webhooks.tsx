import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { listAgents } from '@/api/agents'
import {
  listWebhooks,
  createWebhook,
  deleteWebhook,
  type Webhook,
} from '@/api/webhooks'
import type { Agent } from '@/types'

type WebhookRow = Webhook & { _agentName: string }

export function WebhooksPage() {
  const navigate = useNavigate()
  const [agents, setAgents] = useState<Agent[]>([])
  const [webhooks, setWebhooks] = useState<WebhookRow[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [selectedAgentId, setSelectedAgentId] = useState('')
  const [name, setName] = useState('')
  const [direction, setDirection] = useState<'inbound' | 'outbound'>('inbound')
  const [url, setUrl] = useState('')
  const [creating, setCreating] = useState(false)
  const [copiedSlug, setCopiedSlug] = useState<string | null>(null)

  useEffect(() => {
    listAgents().then(({ agents: list }) => {
      setAgents(list)
      if (list[0]) setSelectedAgentId(list[0].id)
      Promise.allSettled(list.map(a => listWebhooks(a.id))).then(results => {
        const all: WebhookRow[] = []
        results.forEach((r, i) => {
          if (r.status === 'fulfilled') {
            r.value.webhooks.forEach(wh => all.push({ ...wh, _agentName: list[i].name }))
          }
        })
        setWebhooks(all)
        setLoading(false)
      })
    }).catch(() => setLoading(false))
  }, [])

  async function handleCreate() {
    if (!selectedAgentId || !name.trim()) return
    if (direction === 'outbound' && !url.trim()) return
    const agentName = agents.find(a => a.id === selectedAgentId)?.name ?? ''
    setCreating(true)
    try {
      const { webhook } = await createWebhook(selectedAgentId, {
        name: name.trim(),
        direction,
        url: direction === 'outbound' ? url.trim() : undefined,
      })
      setWebhooks(prev => [{ ...webhook, _agentName: agentName }, ...prev])
      setName('')
      setUrl('')
      setDirection('inbound')
      setShowCreate(false)
    } catch { /* ignore */ } finally {
      setCreating(false)
    }
  }

  async function handleDelete(wh: WebhookRow) {
    if (!confirm('Delete this webhook?')) return
    try {
      await deleteWebhook(wh.agent_id, wh.id)
      setWebhooks(prev => prev.filter(w => w.id !== wh.id))
    } catch { /* ignore */ }
  }

  function copyTriggerUrl(slug: string) {
    const triggerUrl = `${window.location.origin}/api/hooks/${slug}`
    navigator.clipboard.writeText(triggerUrl)
    setCopiedSlug(slug)
    setTimeout(() => setCopiedSlug(null), 2000)
  }

  return (
    <div className="min-h-svh bg-background">
      {/* Header */}
      <header className="sticky top-0 z-10 border-b border-border bg-card">
        <div className="mx-auto flex max-w-3xl items-center gap-3 px-4 py-3">
          <button
            onClick={() => navigate(-1)}
            className="flex items-center gap-1.5 rounded-lg p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M10 12L6 8l4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
          <div className="flex items-center gap-2 flex-1 min-w-0">
            <span className="text-xl">🔗</span>
            <h1 className="text-base font-semibold text-foreground">Webhooks</h1>
            <span className="text-xs text-muted-foreground hidden sm:block">— all agents</span>
          </div>
          <Button size="sm" onClick={() => setShowCreate(v => !v)}>
            {showCreate ? 'Cancel' : '+ New Webhook'}
          </Button>
        </div>
      </header>

      <div className="mx-auto max-w-3xl px-4 py-6 space-y-4">
        {/* Create form */}
        {showCreate && (
          <div className="rounded-lg border border-border bg-card p-5 space-y-4">
            <h3 className="text-sm font-semibold text-foreground">New Webhook</h3>

            {/* Agent selector */}
            <div className="space-y-1.5">
              <Label>Agent</Label>
              <select
                value={selectedAgentId}
                onChange={e => setSelectedAgentId(e.target.value)}
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
              >
                {agents.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
              </select>
            </div>

            <div className="space-y-1.5">
              <Label>Name</Label>
              <Input value={name} onChange={e => setName(e.target.value)} placeholder="My Webhook" />
            </div>

            <div className="space-y-1.5">
              <Label>Direction</Label>
              <div className="flex gap-2 flex-wrap">
                <button
                  onClick={() => setDirection('inbound')}
                  className={`rounded-md px-3 py-1.5 text-sm transition-colors ${
                    direction === 'inbound'
                      ? 'bg-primary text-primary-foreground'
                      : 'bg-muted text-muted-foreground hover:text-foreground'
                  }`}
                >
                  Inbound (receive triggers)
                </button>
                <button
                  onClick={() => setDirection('outbound')}
                  className={`rounded-md px-3 py-1.5 text-sm transition-colors ${
                    direction === 'outbound'
                      ? 'bg-primary text-primary-foreground'
                      : 'bg-muted text-muted-foreground hover:text-foreground'
                  }`}
                >
                  Outbound (send notifications)
                </button>
              </div>
            </div>

            {direction === 'inbound' && (
              <p className="rounded-md bg-muted/50 p-3 text-xs text-muted-foreground">
                After saving, you'll get a unique trigger URL:{' '}
                <code className="font-mono">{window.location.origin}/api/hooks/{'<slug>'}</code>
              </p>
            )}

            {direction === 'outbound' && (
              <div className="space-y-1.5">
                <Label>Callback URL</Label>
                <Input
                  value={url}
                  onChange={e => setUrl(e.target.value)}
                  placeholder="https://example.com/callback"
                />
              </div>
            )}

            <Button
              onClick={handleCreate}
              disabled={creating || !name.trim() || (direction === 'outbound' && !url.trim())}
              size="sm"
            >
              {creating ? 'Creating…' : 'Create Webhook'}
            </Button>
          </div>
        )}

        {/* List */}
        {loading ? (
          <div className="py-16 text-center text-sm text-muted-foreground">Loading…</div>
        ) : webhooks.length === 0 && !showCreate ? (
          <div className="py-16 text-center">
            <div className="text-5xl mb-4">🔗</div>
            <p className="text-sm font-medium text-foreground">No webhooks yet</p>
            <p className="mt-2 text-xs text-muted-foreground max-w-sm mx-auto space-y-1">
              <span className="block"><strong>Inbound:</strong> External services send messages to your agent via a unique URL.</span>
              <span className="block"><strong>Outbound:</strong> Your agent sends responses to an external URL.</span>
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {webhooks.map(wh => (
              <div
                key={wh.id}
                className="flex items-center gap-3 rounded-lg border border-border bg-card px-4 py-3"
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium uppercase shrink-0 ${
                      wh.direction === 'inbound'
                        ? 'bg-blue-500/20 text-blue-400'
                        : 'bg-emerald-500/20 text-emerald-400'
                    }`}>
                      {wh.direction}
                    </span>
                    <span className="text-sm font-medium text-foreground truncate">{wh.name || wh.slug}</span>
                    <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-medium text-primary shrink-0">
                      {wh._agentName}
                    </span>
                  </div>
                  {wh.direction === 'inbound' && (
                    <div className="mt-1 flex items-center gap-2">
                      <code className="text-xs text-muted-foreground truncate">/api/hooks/{wh.slug}</code>
                      <button
                        onClick={() => copyTriggerUrl(wh.slug)}
                        className="text-xs text-primary hover:underline shrink-0"
                      >
                        {copiedSlug === wh.slug ? 'Copied!' : 'Copy URL'}
                      </button>
                    </div>
                  )}
                  {wh.direction === 'outbound' && wh.url && (
                    <div className="mt-1 text-xs text-muted-foreground truncate">{wh.url}</div>
                  )}
                </div>
                <button
                  onClick={() => handleDelete(wh)}
                  className="rounded p-1.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors shrink-0"
                >
                  <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
                    <path d="M3 3l8 8M11 3l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                  </svg>
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
