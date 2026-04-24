import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { listWebhooks, createWebhook, deleteWebhook, type Webhook } from '@/api/webhooks'

interface Props {
  agentId: string
}

export function WebhooksPanel({ agentId }: Props) {
  const [webhooks, setWebhooks] = useState<Webhook[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [name, setName] = useState('')
  const [direction, setDirection] = useState<'inbound' | 'outbound'>('inbound')
  const [url, setUrl] = useState('')
  const [creating, setCreating] = useState(false)
  const [copiedSlug, setCopiedSlug] = useState<string | null>(null)

  useEffect(() => {
    loadWebhooks()
  }, [agentId])

  async function loadWebhooks() {
    try {
      const { webhooks: whs } = await listWebhooks(agentId)
      setWebhooks(whs)
    } catch { /* ignore */ } finally {
      setLoading(false)
    }
  }

  async function handleCreate() {
    if (!name.trim()) return
    if (direction === 'outbound' && !url.trim()) return
    setCreating(true)
    try {
      const { webhook } = await createWebhook(agentId, {
        name: name.trim(),
        direction,
        url: direction === 'outbound' ? url.trim() : undefined,
      })
      setWebhooks((prev) => [webhook, ...prev])
      setName('')
      setUrl('')
      setShowCreate(false)
    } catch { /* ignore */ } finally {
      setCreating(false)
    }
  }

  async function handleDelete(whId: string) {
    if (!confirm('Delete this webhook?')) return
    try {
      await deleteWebhook(agentId, whId)
      setWebhooks((prev) => prev.filter((w) => w.id !== whId))
    } catch { /* ignore */ }
  }

  function copyTriggerUrl(slug: string) {
    const triggerUrl = `${window.location.origin}/api/hooks/${slug}`
    navigator.clipboard.writeText(triggerUrl)
    setCopiedSlug(slug)
    setTimeout(() => setCopiedSlug(null), 2000)
  }

  if (loading) return <div className="p-6 text-muted-foreground">Loading...</div>

  return (
    <div className="mx-auto max-w-2xl space-y-6 p-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-foreground">Webhooks</h2>
        <Button size="sm" onClick={() => setShowCreate(!showCreate)}>
          {showCreate ? 'Cancel' : '+ New Webhook'}
        </Button>
      </div>

      {showCreate && (
        <div className="space-y-4 rounded-lg border border-border p-4">
          <div className="space-y-2">
            <Label>Name</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="My Webhook" />
          </div>
          <div className="space-y-2">
            <Label>Direction</Label>
            <div className="flex gap-2">
              <button
                onClick={() => setDirection('inbound')}
                className={`rounded-md px-3 py-1.5 text-sm ${direction === 'inbound' ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground'}`}
              >
                Inbound (receive triggers)
              </button>
              <button
                onClick={() => setDirection('outbound')}
                className={`rounded-md px-3 py-1.5 text-sm ${direction === 'outbound' ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground'}`}
              >
                Outbound (send notifications)
              </button>
            </div>
          </div>
          {direction === 'outbound' && (
            <div className="space-y-2">
              <Label>Callback URL</Label>
              <Input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://example.com/callback" />
            </div>
          )}
          <Button onClick={handleCreate} disabled={creating || !name.trim()}>
            {creating ? 'Creating...' : 'Create Webhook'}
          </Button>
        </div>
      )}

      {webhooks.length === 0 ? (
        <div className="py-12 text-center text-muted-foreground space-y-3">
          <div className="text-4xl">&#128279;</div>
          <div className="text-sm">No webhooks yet.</div>
          <div className="text-xs max-w-md mx-auto space-y-2">
            <p><strong>Inbound:</strong> External services (Teams, Slack, GitHub) send messages to your agent via a unique URL.</p>
            <p><strong>Outbound:</strong> Your agent sends its responses to an external URL. Works with chat, API calls, and scheduled tasks.</p>
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          {webhooks.map((wh) => (
            <div key={wh.id} className="flex items-center justify-between rounded-lg border border-border p-4">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-medium uppercase ${
                    wh.direction === 'inbound' ? 'bg-blue-500/20 text-blue-400' : 'bg-emerald-500/20 text-emerald-400'
                  }`}>
                    {wh.direction}
                  </span>
                  <span className="text-sm font-medium text-foreground">{wh.name || wh.slug}</span>
                </div>
                {wh.direction === 'inbound' && (
                  <div className="mt-1 flex items-center gap-2">
                    <code className="text-xs text-muted-foreground truncate">/api/hooks/{wh.slug}</code>
                    <button
                      onClick={() => copyTriggerUrl(wh.slug)}
                      className="text-xs text-primary hover:underline"
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
                onClick={() => handleDelete(wh.id)}
                className="ml-2 rounded p-1 text-muted-foreground hover:bg-destructive/20 hover:text-destructive"
              >
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                  <path d="M3 3l8 8M11 3l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                </svg>
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
