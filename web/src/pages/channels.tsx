import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { listAgents } from '@/api/agents'
import {
  listChannelConnections,
  createChannelConnection,
  updateChannelConnection,
  deleteChannelConnection,
  type ChannelConnection,
  type ChannelType,
} from '@/api/channels'
import type { Agent } from '@/types'

type ChannelRow = ChannelConnection & { _agentName: string }

const CHANNEL_TYPES: { id: ChannelType; label: string; icon: string; description: string }[] = [
  { id: 'discord', label: 'Discord', icon: '🎮', description: 'Bot responds in Discord channels' },
  { id: 'telegram', label: 'Telegram', icon: '✈️', description: 'Bot responds to Telegram messages' },
  { id: 'sms', label: 'SMS (Twilio)', icon: '📱', description: 'Bot responds to SMS via Twilio' },
  { id: 'email', label: 'Email', icon: '✉️', description: 'Bot responds to incoming emails' },
  { id: 'wechat', label: 'WeChat', icon: '💬', description: 'Bot responds in WeChat Official Account' },
]

const CHANNEL_TYPE_LABELS: Record<ChannelType, string> = {
  discord: 'Discord', telegram: 'Telegram', sms: 'SMS', email: 'Email', wechat: 'WeChat',
}

const CHANNEL_ICONS: Record<ChannelType, string> = {
  discord: '🎮', telegram: '✈️', sms: '📱', email: '✉️', wechat: '💬',
}

type ConfigField = { key: string; label: string; placeholder: string; type?: string }

const CONFIG_FIELDS: Record<ChannelType, ConfigField[]> = {
  discord: [
    { key: 'bot_token', label: 'Bot Token', placeholder: 'Your Discord bot token', type: 'password' },
    { key: 'guild_id', label: 'Server ID (optional)', placeholder: 'Leave empty for all servers' },
    { key: 'channel_ids', label: 'Channel IDs (optional)', placeholder: 'Comma-separated, e.g. 123456,789012' },
  ],
  telegram: [
    { key: 'bot_token', label: 'Bot Token', placeholder: 'Token from @BotFather', type: 'password' },
    { key: 'webhook_url', label: 'Webhook URL', placeholder: 'https://yourserver.com/api/channels/telegram/...' },
    { key: 'webhook_secret', label: 'Webhook Secret (optional)', placeholder: 'Random secret for verification', type: 'password' },
  ],
  sms: [
    { key: 'account_sid', label: 'Account SID', placeholder: 'Twilio Account SID' },
    { key: 'auth_token', label: 'Auth Token', placeholder: 'Twilio Auth Token', type: 'password' },
    { key: 'from_number', label: 'From Number', placeholder: '+1234567890' },
  ],
  email: [
    { key: 'imap_host', label: 'IMAP Host', placeholder: 'imap.gmail.com' },
    { key: 'imap_user', label: 'IMAP Username', placeholder: 'you@example.com' },
    { key: 'imap_pass', label: 'IMAP Password', placeholder: 'App password', type: 'password' },
    { key: 'smtp_host', label: 'SMTP Host', placeholder: 'smtp.gmail.com' },
    { key: 'address', label: 'Email Address', placeholder: 'you@example.com' },
  ],
  wechat: [
    { key: 'app_id', label: 'AppID', placeholder: 'WeChat Official Account AppID' },
    { key: 'app_secret', label: 'AppSecret', placeholder: 'WeChat AppSecret', type: 'password' },
    { key: 'token', label: 'Token', placeholder: 'Verification token (you choose this)' },
    { key: 'encoding_aes_key', label: 'EncodingAESKey (optional)', placeholder: 'For encrypted mode only', type: 'password' },
  ],
}

export function ChannelsPage() {
  const navigate = useNavigate()
  const [agents, setAgents] = useState<Agent[]>([])
  const [connections, setConnections] = useState<ChannelRow[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [selectedAgentId, setSelectedAgentId] = useState('')
  const [selectedType, setSelectedType] = useState<ChannelType>('discord')
  const [name, setName] = useState('')
  const [configValues, setConfigValues] = useState<Record<string, string>>({})
  const [creating, setCreating] = useState(false)
  const [togglingId, setTogglingId] = useState<string | null>(null)

  useEffect(() => {
    listAgents().then(({ agents: list }) => {
      setAgents(list)
      const firstAgent = list[0]
      if (firstAgent) setSelectedAgentId(firstAgent.id)
      Promise.allSettled(list.map(a => listChannelConnections(a.id))).then(results => {
        const all: ChannelRow[] = []
        results.forEach((r, i) => {
          if (r.status === 'fulfilled') {
            r.value.connections.forEach(c => all.push({ ...c, _agentName: list[i].name }))
          }
        })
        setConnections(all)
        setLoading(false)
      })
    }).catch(() => setLoading(false))
  }, [])

  function handleTypeChange(type: ChannelType) {
    setSelectedType(type)
    setConfigValues({})
  }

  async function handleCreate() {
    if (!selectedAgentId) return
    const agentName = agents.find(a => a.id === selectedAgentId)?.name ?? ''
    setCreating(true)
    try {
      const config: Record<string, unknown> = { ...configValues }
      if (selectedType === 'discord' && typeof config.channel_ids === 'string') {
        config.channel_ids = (config.channel_ids as string).split(',').map(s => s.trim()).filter(Boolean)
      }
      const { connection } = await createChannelConnection(selectedAgentId, {
        channel_type: selectedType,
        name: name.trim() || CHANNEL_TYPE_LABELS[selectedType],
        config: config as Record<string, string>,
        is_active: true,
      })
      setConnections(prev => [{ ...connection, _agentName: agentName }, ...prev])
      setShowCreate(false)
      setName('')
      setConfigValues({})
    } catch { /* ignore */ } finally {
      setCreating(false)
    }
  }

  async function handleToggle(conn: ChannelRow) {
    setTogglingId(conn.id)
    try {
      const { connection: updated } = await updateChannelConnection(conn.agent_id, conn.id, {
        is_active: !conn.is_active,
      })
      setConnections(prev => prev.map(c => c.id === conn.id ? { ...updated, _agentName: conn._agentName } : c))
    } catch { /* ignore */ } finally {
      setTogglingId(null)
    }
  }

  async function handleDelete(conn: ChannelRow) {
    if (!confirm('Delete this channel connection?')) return
    try {
      await deleteChannelConnection(conn.agent_id, conn.id)
      setConnections(prev => prev.filter(c => c.id !== conn.id))
    } catch { /* ignore */ }
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
            <span className="text-xl">💬</span>
            <h1 className="text-base font-semibold text-foreground">Channels</h1>
            <span className="text-xs text-muted-foreground hidden sm:block">— all agents</span>
          </div>
          <Button size="sm" onClick={() => setShowCreate(v => !v)}>
            {showCreate ? 'Cancel' : '+ Add Channel'}
          </Button>
        </div>
      </header>

      <div className="mx-auto max-w-3xl px-4 py-6 space-y-4">
        {/* Create form */}
        {showCreate && (
          <div className="rounded-lg border border-border bg-card p-5 space-y-4">
            <h3 className="text-sm font-semibold text-foreground">New Channel Connection</h3>

            {/* Agent selector */}
            <div className="space-y-1.5">
              <Label>Agent</Label>
              <select
                value={selectedAgentId}
                onChange={e => setSelectedAgentId(e.target.value)}
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
              >
                {agents.map(a => (
                  <option key={a.id} value={a.id}>{a.name}</option>
                ))}
              </select>
            </div>

            {/* Type selector */}
            <div className="grid grid-cols-3 gap-2 sm:grid-cols-5">
              {CHANNEL_TYPES.map(ct => (
                <button
                  key={ct.id}
                  onClick={() => handleTypeChange(ct.id)}
                  className={`flex flex-col items-center gap-1 rounded-lg border p-3 text-center text-xs transition-colors ${
                    selectedType === ct.id
                      ? 'border-primary bg-primary/10 text-foreground'
                      : 'border-border text-muted-foreground hover:border-primary/50 hover:text-foreground'
                  }`}
                >
                  <span className="text-xl">{ct.icon}</span>
                  <span className="font-medium">{ct.label}</span>
                </button>
              ))}
            </div>

            <p className="text-xs text-muted-foreground">
              {CHANNEL_TYPES.find(ct => ct.id === selectedType)?.description}
            </p>

            <div className="space-y-1.5">
              <Label>Connection Name</Label>
              <Input
                placeholder={CHANNEL_TYPE_LABELS[selectedType]}
                value={name}
                onChange={e => setName(e.target.value)}
              />
            </div>

            {CONFIG_FIELDS[selectedType].map(field => (
              <div key={field.key} className="space-y-1.5">
                <Label>{field.label}</Label>
                <Input
                  type={field.type ?? 'text'}
                  placeholder={field.placeholder}
                  value={configValues[field.key] ?? ''}
                  onChange={e => setConfigValues(prev => ({ ...prev, [field.key]: e.target.value }))}
                />
              </div>
            ))}

            {selectedType === 'telegram' && (
              <p className="rounded-md bg-muted/50 p-3 text-xs text-muted-foreground">
                Set the Webhook URL to <code className="font-mono">https://your-server/api/channels/telegram/&#123;connection_id&#125;/webhook</code> after saving.
              </p>
            )}
            {selectedType === 'sms' && (
              <p className="rounded-md bg-muted/50 p-3 text-xs text-muted-foreground">
                In Twilio, set your number's inbound webhook to <code className="font-mono">https://your-server/api/channels/sms/&#123;connection_id&#125;/webhook</code> after saving.
              </p>
            )}
            {selectedType === 'wechat' && (
              <p className="rounded-md bg-muted/50 p-3 text-xs text-muted-foreground">
                In the WeChat Official Account dashboard, set the server URL to{' '}
                <code className="font-mono">https://your-server/api/channels/wechat/&#123;connection_id&#125;/webhook</code>{' '}
                after saving.
              </p>
            )}

            <div className="flex gap-2">
              <Button onClick={handleCreate} disabled={creating || !selectedAgentId} size="sm">
                {creating ? 'Saving…' : 'Save Connection'}
              </Button>
              <Button variant="outline" size="sm" onClick={() => { setShowCreate(false); setConfigValues({}) }}>
                Cancel
              </Button>
            </div>
          </div>
        )}

        {/* List */}
        {loading ? (
          <div className="py-16 text-center text-sm text-muted-foreground">Loading…</div>
        ) : connections.length === 0 && !showCreate ? (
          <div className="py-16 text-center">
            <div className="text-5xl mb-4">🔌</div>
            <p className="text-sm font-medium text-foreground">No channel connections yet</p>
            <p className="mt-1 text-xs text-muted-foreground">
              Add one above to let your agents respond on Discord, Telegram, SMS, WeChat, or email
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {connections.map(conn => (
              <div
                key={conn.id}
                className="flex items-center gap-3 rounded-lg border border-border bg-card px-4 py-3"
              >
                <span className="text-xl shrink-0">{CHANNEL_ICONS[conn.channel_type] ?? '🔗'}</span>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-medium text-foreground truncate">{conn.name}</span>
                    <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] font-medium text-muted-foreground uppercase tracking-wide shrink-0">
                      {CHANNEL_TYPE_LABELS[conn.channel_type]}
                    </span>
                    <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-medium text-primary shrink-0">
                      {conn._agentName}
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5 mt-0.5">
                    <span className={`h-1.5 w-1.5 rounded-full ${conn.is_active ? 'bg-emerald-500' : 'bg-zinc-400'}`} />
                    <span className="text-[11px] text-muted-foreground">{conn.is_active ? 'Active' : 'Inactive'}</span>
                    <span className="text-[10px] text-muted-foreground/50 font-mono ml-1">{conn.id}</span>
                  </div>
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  <button
                    onClick={() => handleToggle(conn)}
                    disabled={togglingId === conn.id}
                    className={`rounded px-2 py-1 text-[11px] font-medium transition-colors ${
                      conn.is_active
                        ? 'text-orange-600 hover:bg-orange-50 dark:hover:bg-orange-950/20'
                        : 'text-emerald-600 hover:bg-emerald-50 dark:hover:bg-emerald-950/20'
                    }`}
                  >
                    {togglingId === conn.id ? '…' : conn.is_active ? 'Pause' : 'Activate'}
                  </button>
                  <button
                    onClick={() => handleDelete(conn)}
                    className="rounded p-1.5 text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive"
                  >
                    <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
                      <path d="M3 3l8 8M11 3l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                    </svg>
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
