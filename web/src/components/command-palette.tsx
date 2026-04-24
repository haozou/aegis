import { useEffect, useState, useMemo } from 'react'
import { Command } from 'cmdk'
import { useNavigate } from 'react-router-dom'
import { listAgents } from '@/api/agents'
import { listModels } from '@/api/models'
import { listConversations } from '@/api/conversations'
import { useAuthStore } from '@/stores/auth-store'
import { toggleTheme } from '@/lib/theme'
import type { Agent, Conversation } from '@/types'

const SELECTED_AGENT_KEY = 'aegis_selected_agent'

interface Props {
  open: boolean
  onClose: () => void
}

export function CommandPalette({ open, onClose }: Props) {
  const navigate = useNavigate()
  const logout = useAuthStore((s) => s.logout)

  const [agents, setAgents] = useState<Agent[]>([])
  const [models, setModels] = useState<string[]>([])
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [search, setSearch] = useState('')

  // Load data when opened
  useEffect(() => {
    if (!open) return
    listAgents().then(({ agents }) => setAgents(agents)).catch(() => {})
    listModels().then(({ models }) => setModels(models)).catch(() => {})
    listConversations().then(({ conversations }) => setConversations(conversations)).catch(() => {})
  }, [open])

  const close = () => {
    setSearch('')
    onClose()
  }

  function switchAgent(agentId: string) {
    localStorage.setItem(SELECTED_AGENT_KEY, agentId)
    navigate('/')
    // Force reload so chat page picks up the new agent cleanly
    setTimeout(() => window.location.reload(), 10)
    close()
  }

  function goTo(path: string) {
    navigate(path)
    close()
  }

  function newChat() {
    navigate('/')
    window.location.search = ''
    close()
  }

  function selectConversation(convId: string) {
    navigate(`/?conv=${convId}`)
    setTimeout(() => window.location.reload(), 10)
    close()
  }

  // Fuzzy search is built into cmdk via its `value` matching — just filter what we render
  const conversationsSorted = useMemo(() => {
    return [...conversations].sort((a, b) =>
      new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
    ).slice(0, 20)
  }, [conversations])

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-[100] flex items-start justify-center pt-[15vh] bg-black/40 backdrop-blur-sm"
      onClick={close}
    >
      <Command
        label="Command menu"
        className="w-full max-w-xl rounded-xl border border-border bg-popover shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2.5 border-b border-border px-4">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" className="text-muted-foreground/50">
            <circle cx="7" cy="7" r="5" stroke="currentColor" strokeWidth="1.5"/>
            <path d="M11 11l3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
          </svg>
          <Command.Input
            value={search}
            onValueChange={setSearch}
            placeholder="Type a command or search…"
            autoFocus
            className="flex-1 border-0 bg-transparent py-3.5 text-sm text-foreground placeholder:text-muted-foreground/40 focus:outline-none"
          />
          <kbd className="hidden sm:inline text-[10px] text-muted-foreground/50 font-mono">ESC</kbd>
        </div>
        <Command.List className="max-h-[380px] overflow-y-auto p-1.5">
          <Command.Empty className="py-8 text-center text-sm text-muted-foreground/60">
            No results found.
          </Command.Empty>

          {/* Actions */}
          <Command.Group heading="Actions" className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-[10px] [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-widest [&_[cmdk-group-heading]]:text-muted-foreground/50">
            <CmdItem value="new chat" onSelect={newChat} icon="✚">New chat</CmdItem>
            <CmdItem value="toggle theme dark light" onSelect={() => { toggleTheme(); close() }} icon="🌓">Toggle theme</CmdItem>
            <CmdItem value="logout sign out" onSelect={() => { logout(); navigate('/login'); close() }} icon="→">Sign out</CmdItem>
          </Command.Group>

          {/* Navigation */}
          <Command.Group heading="Navigate" className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-[10px] [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-widest [&_[cmdk-group-heading]]:text-muted-foreground/50">
            <CmdItem value="go chat home" onSelect={() => goTo('/')} icon="💬">Chat</CmdItem>
            <CmdItem value="go dashboard agents" onSelect={() => goTo('/dashboard')} icon="📊">Dashboard</CmdItem>
            <CmdItem value="go channels" onSelect={() => goTo('/channels')} icon="📨">Channels</CmdItem>
            <CmdItem value="go schedules cron" onSelect={() => goTo('/schedules')} icon="⏰">Schedules</CmdItem>
            <CmdItem value="go webhooks" onSelect={() => goTo('/webhooks')} icon="🪝">Webhooks</CmdItem>
            <CmdItem value="go knowledge base" onSelect={() => goTo('/knowledge')} icon="📚">Knowledge</CmdItem>
          </Command.Group>

          {/* Switch agent */}
          {agents.length > 0 && (
            <Command.Group heading="Switch agent" className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-[10px] [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-widest [&_[cmdk-group-heading]]:text-muted-foreground/50">
              {agents.map(a => (
                <CmdItem key={a.id} value={`agent ${a.name} ${a.model}`} onSelect={() => switchAgent(a.id)} icon="🤖">
                  <span>{a.name}</span>
                  <span className="ml-auto text-[10px] text-muted-foreground/50 font-mono">{a.model}</span>
                </CmdItem>
              ))}
            </Command.Group>
          )}

          {/* Switch model for current agent */}
          {models.length > 0 && (
            <Command.Group heading="Model" className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-[10px] [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-widest [&_[cmdk-group-heading]]:text-muted-foreground/50">
              {models.slice(0, 12).map(m => (
                <CmdItem key={m} value={`model ${m}`} onSelect={() => close()} icon="🧠">
                  <span className="font-mono text-xs">{m}</span>
                </CmdItem>
              ))}
            </Command.Group>
          )}

          {/* Recent chats */}
          {conversationsSorted.length > 0 && (
            <Command.Group heading="Recent chats" className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-[10px] [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-widest [&_[cmdk-group-heading]]:text-muted-foreground/50">
              {conversationsSorted.map(c => (
                <CmdItem key={c.id} value={`chat ${c.title}`} onSelect={() => selectConversation(c.id)} icon="💬">
                  <span className="truncate">{c.title}</span>
                </CmdItem>
              ))}
            </Command.Group>
          )}
        </Command.List>
      </Command>
    </div>
  )
}

function CmdItem({
  value, onSelect, icon, children,
}: {
  value: string
  onSelect: () => void
  icon?: string
  children: React.ReactNode
}) {
  return (
    <Command.Item
      value={value}
      onSelect={onSelect}
      className="flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm text-foreground cursor-pointer data-[selected=true]:bg-muted data-[selected=true]:text-foreground transition-colors"
    >
      {icon && <span className="text-base leading-none opacity-70 shrink-0 w-4 text-center">{icon}</span>}
      <div className="flex-1 min-w-0 flex items-center gap-2">{children}</div>
    </Command.Item>
  )
}
