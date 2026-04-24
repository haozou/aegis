import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  listChannelConnections,
  createChannelConnection,
  updateChannelConnection,
  deleteChannelConnection,
  type ChannelConnection,
  type ChannelType,
} from '@/api/channels'

interface Props {
  agentId: string
}

const CHANNEL_TYPES: { id: ChannelType; label: string; icon: string; description: string }[] = [
  { id: 'discord', label: 'Discord', icon: '🎮', description: 'Bot responds in Discord channels' },
  { id: 'telegram', label: 'Telegram', icon: '✈️', description: 'Bot responds to Telegram messages' },
  { id: 'sms', label: 'SMS (Twilio)', icon: '📱', description: 'Bot responds to SMS via Twilio' },
  { id: 'email', label: 'Email', icon: '✉️', description: 'Bot responds to incoming emails' },
  { id: 'wechat', label: 'WeChat', icon: '💬', description: 'Bot responds in WeChat Official Account' },
]

const CHANNEL_TYPE_LABELS: Record<ChannelType, string> = {
  discord: 'Discord',
  telegram: 'Telegram',
  sms: 'SMS',
  email: 'Email',
  wechat: 'WeChat',
}

const CHANNEL_ICONS: Record<ChannelType, string> = {
  discord: '🎮',
  telegram: '✈️',
  sms: '📱',
  email: '✉️',
  wechat: '💬',
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

export function ChannelConnectionsPanel({ agentId }: Props) {
  const [connections, setConnections] = useState<ChannelConnection[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [selectedType, setSelectedType] = useState<ChannelType>('discord')
  const [name, setName] = useState('')
  const [configValues, setConfigValues] = useState<Record<string, string>>({})
  const [creating, setCreating] = useState(false)
  const [togglingId, setTogglingId] = useState<string | null>(null)

  useEffect(() => {
    loadConnections()
  }, [agentId])

  async function loadConnections() {
    setLoading(true)
    try {
      const { connections: list } = await listChannelConnections(agentId)
      setConnections(list)
    } catch { /* ignore */ } finally {
      setLoading(false)
    }
  }

  function handleTypeChange(type: ChannelType) {
    setSelectedType(type)
    setConfigValues({})
  }

  async function handleCreate() {
    setCreating(true)
    try {
      // Parse channel_ids as array for discord
      const config: Record<string, unknown> = { ...configValues }
      if (selectedType === 'discord' && typeof config.channel_ids === 'string') {
        config.channel_ids = (config.channel_ids as string)
          .split(',').map(s => s.trim()).filter(Boolean)
      }

      const { connection } = await createChannelConnection(agentId, {
        channel_type: selectedType,
        name: name.trim() || CHANNEL_TYPE_LABELS[selectedType],
        config: config as Record<string, string>,
        is_active: true,
      })
      setConnections(prev => [connection, ...prev])
      setShowCreate(false)
      setName('')
      setConfigValues({})
    } catch { /* ignore */ } finally {
      setCreating(false)
    }
  }

  async function handleToggle(conn: ChannelConnection) {
    setTogglingId(conn.id)
    try {
      const { connection: updated } = await updateChannelConnection(agentId, conn.id, {
        is_active: !conn.is_active,
      })
      setConnections(prev => prev.map(c => c.id === conn.id ? updated : c))
    } catch { /* ignore */ } finally {
      setTogglingId(null)
    }
  }

  async function handleDelete(id: string) {
    if (!confirm('Delete this channel connection?')) return
    try {
      await deleteChannelConnection(agentId, id)
      setConnections(prev => prev.filter(c => c.id !== id))
    } catch { /* ignore */ }
  }

  return (
    <div className="mx-auto max-w-2xl px-4 py-8">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-foreground">Channel Connections</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Connect this agent to Discord, Telegram, SMS, WeChat, or email
          </p>
        </div>
        {!showCreate && (
          <Button onClick={() => setShowCreate(true)} size="sm">
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none" className="mr-1.5">
              <path d="M8 3v10M3 8h10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
            Add Channel
          </Button>
        )}
      </div>

      {/* Create form */}
      {showCreate && (
        <div className="mb-6 rounded-lg border border-border bg-card p-5 space-y-4">
          <h3 className="text-sm font-medium text-foreground">New Channel Connection</h3>

          {/* Type selector */}
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
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

          {/* Name */}
          <div className="space-y-1.5">
            <Label htmlFor="conn-name">Connection Name</Label>
            <Input
              id="conn-name"
              placeholder={CHANNEL_TYPE_LABELS[selectedType]}
              value={name}
              onChange={e => setName(e.target.value)}
            />
          </div>

          {/* Config fields */}
          {CONFIG_FIELDS[selectedType].map(field => (
            <div key={field.key} className="space-y-1.5">
              <Label htmlFor={`cfg-${field.key}`}>{field.label}</Label>
              <Input
                id={`cfg-${field.key}`}
                type={field.type ?? 'text'}
                placeholder={field.placeholder}
                value={configValues[field.key] ?? ''}
                onChange={e => setConfigValues(prev => ({ ...prev, [field.key]: e.target.value }))}
              />
            </div>
          ))}

          {/* Telegram webhook note */}
          {selectedType === 'telegram' && (
            <p className="rounded-md bg-muted/50 p-3 text-xs text-muted-foreground">
              Set the Webhook URL to <code className="font-mono">https://your-server/api/channels/telegram/&#123;connection_id&#125;/webhook</code> after saving. You'll find the connection ID in the list below.
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
              after saving. Use the same <strong>Token</strong> value you entered above. Enable the Customer Service (客服) API to allow async replies.
            </p>
          )}

          <div className="flex gap-2">
            <Button onClick={handleCreate} disabled={creating} size="sm">
              {creating ? 'Connecting…' : 'Save Connection'}
            </Button>
            <Button variant="outline" size="sm" onClick={() => { setShowCreate(false); setConfigValues({}) }}>
              Cancel
            </Button>
          </div>
        </div>
      )}

      {/* Connections list */}
      {loading ? (
        <div className="py-10 text-center text-sm text-muted-foreground">Loading…</div>
      ) : connections.length === 0 && !showCreate ? (
        <div className="py-16 text-center">
          <div className="text-4xl mb-3">🔌</div>
          <p className="text-sm text-muted-foreground">No channel connections yet</p>
          <p className="mt-1 text-xs text-muted-foreground">
            Add one above to let your agent respond on Discord, Telegram, SMS, WeChat, or email
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {connections.map(conn => (
            <div
              key={conn.id}
              className="flex items-center gap-3 rounded-lg border border-border bg-card px-4 py-3"
            >
              <span className="text-xl">{CHANNEL_ICONS[conn.channel_type] ?? '🔗'}</span>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-foreground truncate">{conn.name}</span>
                  <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide">
                    {CHANNEL_TYPE_LABELS[conn.channel_type]}
                  </span>
                </div>
                <div className="flex items-center gap-1.5 mt-0.5">
                  <span className={`h-1.5 w-1.5 rounded-full ${conn.is_active ? 'bg-emerald-500' : 'bg-zinc-400'}`} />
                  <span className="text-[11px] text-muted-foreground">{conn.is_active ? 'Active' : 'Inactive'}</span>
                  <span className="text-[10px] text-muted-foreground/50 font-mono ml-1">{conn.id}</span>
                </div>
              </div>
              <div className="flex items-center gap-1 shrink-0">
                {/* Toggle */}
                <button
                  onClick={() => handleToggle(conn)}
                  disabled={togglingId === conn.id}
                  className={`rounded px-2 py-1 text-[11px] font-medium transition-colors ${
                    conn.is_active
                      ? 'text-orange-600 hover:bg-orange-50 dark:hover:bg-orange-950/20'
                      : 'text-emerald-600 hover:bg-emerald-50 dark:hover:bg-emerald-950/20'
                  }`}
                  title={conn.is_active ? 'Pause' : 'Activate'}
                >
                  {togglingId === conn.id ? '…' : conn.is_active ? 'Pause' : 'Activate'}
                </button>
                {/* Delete */}
                <button
                  onClick={() => handleDelete(conn.id)}
                  className="rounded p-1.5 text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive"
                  title="Delete"
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
  )
}
