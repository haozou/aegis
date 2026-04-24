import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import { useAuthStore } from '@/stores/auth-store'
import { listConversations, createConversation, deleteConversation } from '@/api/conversations'
import type { Conversation } from '@/types'

interface SidebarProps {
  activeId?: string
  onSelect: (id: string) => void
}

export function Sidebar({ activeId, onSelect }: SidebarProps) {
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [loading, setLoading] = useState(true)
  const { user, logout } = useAuthStore()
  const navigate = useNavigate()

  async function loadConversations() {
    try {
      const { conversations: convs } = await listConversations()
      setConversations(convs)
    } catch {
      // ignore
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadConversations()
  }, [])

  async function handleNewChat() {
    try {
      const { conversation } = await createConversation()
      setConversations((prev) => [conversation, ...prev])
      onSelect(conversation.id)
    } catch {
      // ignore
    }
  }

  async function handleDelete(e: React.MouseEvent, id: string) {
    e.stopPropagation()
    try {
      await deleteConversation(id)
      setConversations((prev) => prev.filter((c) => c.id !== id))
      if (activeId === id) {
        onSelect('')
      }
    } catch {
      // ignore
    }
  }

  function handleLogout() {
    logout()
    navigate('/login', { replace: true })
  }

  function formatDate(dateStr: string) {
    const date = new Date(dateStr)
    const now = new Date()
    const diffMs = now.getTime() - date.getTime()
    const diffDays = Math.floor(diffMs / 86400000)

    if (diffDays === 0) return 'Today'
    if (diffDays === 1) return 'Yesterday'
    if (diffDays < 7) return `${diffDays}d ago`
    return date.toLocaleDateString()
  }

  return (
    <div className="flex h-full w-64 flex-col border-r border-border bg-sidebar">
      {/* Header */}
      <div className="flex items-center justify-between p-4">
        <h2 className="text-lg font-semibold text-foreground">Aegis</h2>
      </div>

      {/* New Chat Button */}
      <div className="px-3 pb-3">
        <Button
          onClick={handleNewChat}
          variant="outline"
          className="w-full justify-start gap-2 text-sm"
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M8 3v10M3 8h10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
          New Chat
        </Button>
      </div>

      <Separator />

      {/* Conversation List */}
      <ScrollArea className="flex-1">
        <div className="p-2">
          {loading ? (
            <div className="px-3 py-2 text-sm text-muted-foreground">Loading...</div>
          ) : conversations.length === 0 ? (
            <div className="px-3 py-8 text-center text-sm text-muted-foreground">
              No conversations yet
            </div>
          ) : (
            conversations.map((conv) => (
              <button
                key={conv.id}
                onClick={() => onSelect(conv.id)}
                className={`group mb-0.5 flex w-full items-center justify-between rounded-md px-3 py-2 text-left text-sm transition-colors ${
                  activeId === conv.id
                    ? 'bg-accent text-accent-foreground'
                    : 'text-sidebar-foreground hover:bg-sidebar-accent'
                }`}
              >
                <div className="min-w-0 flex-1">
                  <div className="truncate font-medium">{conv.title}</div>
                  <div className="truncate text-xs text-muted-foreground">
                    {formatDate(conv.updated_at)}
                  </div>
                </div>
                <button
                  onClick={(e) => handleDelete(e, conv.id)}
                  className="ml-2 hidden rounded p-1 text-muted-foreground opacity-0 transition-opacity hover:bg-destructive/20 hover:text-destructive group-hover:opacity-100"
                  title="Delete"
                >
                  <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                    <path d="M3 3l8 8M11 3l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                  </svg>
                </button>
              </button>
            ))
          )}
        </div>
      </ScrollArea>

      <Separator />

      {/* User Info */}
      <div className="flex items-center gap-3 p-3">
        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary text-sm font-medium text-primary-foreground">
          {user?.display_name?.[0]?.toUpperCase() || user?.username?.[0]?.toUpperCase() || '?'}
        </div>
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-medium text-foreground">
            {user?.display_name || user?.username}
          </div>
          <div className="truncate text-xs text-muted-foreground">{user?.email}</div>
        </div>
        <button
          onClick={handleLogout}
          className="rounded p-1 text-muted-foreground transition-colors hover:text-foreground"
          title="Sign out"
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M6 14H3a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1h3M11 11l3-3-3-3M14 8H6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </div>
    </div>
  )
}
