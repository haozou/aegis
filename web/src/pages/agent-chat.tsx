import { useEffect, useState, useRef, useCallback, useMemo } from 'react'
import { useParams, useNavigate, useSearchParams, Link } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Button } from '@/components/ui/button'
import { UserMenu } from '@/components/user-menu'
import { getAgent } from '@/api/agents'
import { listConversations, listMessages, deleteConversation } from '@/api/conversations'
import { getAccessToken } from '@/api/client'
import { AgentSettingsPanel } from '@/components/agent/settings-panel'
import { WebhooksPanel } from '@/components/agent/webhooks-panel'
import { SchedulesPanel } from '@/components/agent/schedules-panel'
import { KnowledgePanel } from '@/components/agent/knowledge-panel'
import { ToolCallBlock } from '@/components/agent/tool-call-block'
import type { Agent, Conversation, Message, StreamEvent, WsMessage, ToolCall } from '@/types'

type Tab = 'chat' | 'settings' | 'webhooks' | 'schedules' | 'knowledge'

export function AgentChatPage() {
  const { agentId } = useParams<{ agentId: string }>()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const [agent, setAgent] = useState<Agent | null>(null)
  const [activeTab, setActiveTab] = useState<Tab>('chat')
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => localStorage.getItem('aegis_sidebar_collapsed') === 'true')
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [conversationId, setConversationId] = useState<string | null>(searchParams.get('conv'))
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [streamingText, setStreamingText] = useState('')
  const [connected, setConnected] = useState(false)
  const [error, setError] = useState('')
  const [tokenUsage, setTokenUsage] = useState({ totalInput: 0, totalOutput: 0, lastInput: 0, lastOutput: 0 })

  // Tool calls
  const [streamToolCalls, setStreamToolCalls] = useState<ToolCall[]>([])
  const [toolPanelOpen, setToolPanelOpen] = useState(true)

  // MCP auth
  const [mcpAuthRequest, setMcpAuthRequest] = useState<{
    serverId: string; message: string; authUrl?: string; deviceCode?: string
  } | null>(null)

  const wsRef = useRef<WebSocket | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const toolPanelBottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const streamingTextRef = useRef('')
  const skipFetchRef = useRef(0)
  const toolCallMapRef = useRef<Map<string, ToolCall>>(new Map())
  const toolCallOrderRef = useRef<string[]>([])

  // Compute all tool calls from messages + streaming for the right panel
  const allToolCalls = useMemo(() => {
    const fromMessages: ToolCall[] = []
    // Build a map of tool_call_id → output from tool role messages
    const toolOutputs: Record<string, string> = {}
    for (const msg of messages) {
      if (msg.role === 'tool' && msg.tool_call_id) {
        toolOutputs[msg.tool_call_id] = getTextContent(msg)
      }
    }
    for (const msg of messages) {
      if (msg.role === 'assistant' && msg.tool_calls) {
        for (const tc of msg.tool_calls as ToolCall[]) {
          // Merge output from tool result messages if available
          const merged = { ...tc }
          if (!merged.output && toolOutputs[tc.id]) {
            merged.output = toolOutputs[tc.id]
            merged.status = 'done'
          }
          if (merged.status === undefined && merged.output !== undefined) {
            merged.status = merged.isError || merged.is_error ? 'error' : 'done'
          }
          fromMessages.push(merged)
        }
      }
    }
    return [...fromMessages, ...streamToolCalls]
  }, [messages, streamToolCalls])

  function autoResize() {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 200) + 'px'
  }

  useEffect(() => { autoResize() }, [input])

  useEffect(() => {
    if (!agentId) return
    getAgent(agentId).then(({ agent }) => setAgent(agent)).catch(() => navigate('/'))
  }, [agentId, navigate])

  function syncToolCallsToState() {
    const ordered = toolCallOrderRef.current.map(id => toolCallMapRef.current.get(id)!).filter(Boolean)
    setStreamToolCalls([...ordered])
  }

  // Connect WebSocket
  useEffect(() => {
    if (!agentId) return
    const token = getAccessToken()
    if (!token) { navigate('/login'); return }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${protocol}//${window.location.host}/ws/agents/${agentId}/chat`)
    wsRef.current = ws

    ws.onopen = () => { ws.send(JSON.stringify({ type: 'auth', token })) }

    ws.onmessage = (event) => {
      const data: WsMessage = JSON.parse(event.data)
      switch (data.type) {
        case 'auth_ok':
          setConnected(true); setError('')
          // If we have a conversation selected, try to resume any in-progress stream
          // Read directly from URL params (not state, which may be stale in closure)
          {
            const convFromUrl = new URLSearchParams(window.location.search).get('conv')
            if (convFromUrl) {
              // Load saved messages (user question + any saved intermediate results)
              listMessages(convFromUrl).then(({ messages: msgs }) => setMessages(msgs)).catch(() => {})
              // Try to resume active stream (will replay buffered events)
              streamingTextRef.current = ''
              setStreamingText('')
              toolCallMapRef.current.clear()
              toolCallOrderRef.current = []
              setStreamToolCalls([])
              setStreaming(false)
              ws.send(JSON.stringify({ type: 'resume', conversation_id: convFromUrl }))
            }
          }
          break
        case 'no_active_stream':
          // No in-progress stream — reload messages from DB
          setStreaming(false)
          {
            const convId = (data.conversation_id as string) || new URLSearchParams(window.location.search).get('conv')
            if (convId) {
              listMessages(convId).then(({ messages: msgs }) => setMessages(msgs)).catch(() => {})
            }
          }
          break
        case 'conversation_created': {
          const newConvId = data.conversation_id as string
          skipFetchRef.current += 1
          setConversationId(newConvId)
          setSearchParams({ conv: newConvId }, { replace: true })
          setConversations((prev) => [{
            id: newConvId, title: data.title as string,
            created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
            provider: agent?.provider || 'anthropic', model: agent?.model || '',
            system_prompt: null, user_id: null, agent_id: agentId!, metadata: {},
          }, ...prev])
          break
        }
        case 'tool_start': {
          setStreaming(true)  // Ensure streaming state on resume
          const evt = data as StreamEvent
          const toolId = evt.tool_id || `tool_${Date.now()}`
          const toolName = evt.tool_name || 'unknown'
          const existing = toolCallMapRef.current.get(toolId)
          if (existing) {
            existing.input = evt.tool_input || existing.input
          } else {
            const tc: ToolCall = { id: toolId, name: toolName, input: evt.tool_input || undefined, status: 'running' }
            toolCallMapRef.current.set(toolId, tc)
            toolCallOrderRef.current.push(toolId)
          }
          syncToolCallsToState()
          break
        }
        case 'tool_result': {
          const evt = data as StreamEvent
          const toolId = evt.tool_id || ''
          const existing = toolCallMapRef.current.get(toolId)
          if (existing) {
            existing.output = evt.tool_output || ''
            existing.isError = evt.is_error || false
            existing.status = evt.is_error ? 'error' : 'done'
          }
          syncToolCallsToState()
          break
        }
        case 'text_delta': {
          setStreaming(true)  // Ensure streaming state on resume
          const deltaText = (data as StreamEvent).text || ''
          streamingTextRef.current += deltaText
          setStreamingText(streamingTextRef.current)
          break
        }
        case 'done': {
          const usage = (data as StreamEvent).usage
          if (usage) {
            setTokenUsage((prev) => ({
              totalInput: prev.totalInput + (usage.input || 0),
              totalOutput: prev.totalOutput + (usage.output || 0),
              lastInput: usage.input || 0, lastOutput: usage.output || 0,
            }))
          }
          const finalText = streamingTextRef.current
          const finalToolCalls = toolCallOrderRef.current.map(id => toolCallMapRef.current.get(id)!).filter(Boolean)
          if (finalText || finalToolCalls.length > 0) {
            setMessages((msgs) => [...msgs, {
              id: (data as StreamEvent).message_id || `msg_${Date.now()}`,
              conversation_id: '', role: 'assistant' as const, content: finalText,
              tool_calls: finalToolCalls.length > 0 ? finalToolCalls : null,
              tool_call_id: null,
              created_at: new Date().toISOString(),
              tokens_used: (usage?.input || 0) + (usage?.output || 0), metadata: {},
            } satisfies Message])
          }
          streamingTextRef.current = ''; setStreamingText(''); setStreaming(false)
          toolCallMapRef.current.clear(); toolCallOrderRef.current = []
          setStreamToolCalls([])
          break
        }
        case 'error':
          setError((data as StreamEvent).error || 'Unknown error')
          setStreaming(false); streamingTextRef.current = ''; setStreamingText('')
          toolCallMapRef.current.clear(); toolCallOrderRef.current = []; setStreamToolCalls([])
          break
        case 'cancelled':
          setStreaming(false); streamingTextRef.current = ''; setStreamingText('')
          toolCallMapRef.current.clear(); toolCallOrderRef.current = []; setStreamToolCalls([])
          break
        case 'mcp_auth_required': {
          const serverId = data.server_id as string
          const message = data.message as string
          if (message) {
            const urlMatch = message.match(/(https?:\/\/[^\s"'<>]+)/i)
            const authUrl = urlMatch ? urlMatch[1] : undefined
            const codeMatch = message.match(/code[:\s]+([A-Z0-9]{6,12})/i)
            const deviceCode = codeMatch ? codeMatch[1] : undefined
            setMcpAuthRequest({ serverId, message, authUrl, deviceCode })
          }
          break
        }
      }
    }

    ws.onclose = () => { setConnected(false) }
    ws.onerror = () => { setError('WebSocket connection failed'); setConnected(false) }
    return () => { ws.close(); wsRef.current = null }
  }, [agentId, navigate])

  useEffect(() => {
    if (!agentId) return
    listConversations()
      .then(({ conversations: convs }) => setConversations(convs.filter((c) => c.agent_id === agentId)))
      .catch(() => {})
  }, [agentId])

  useEffect(() => {
    if (!conversationId) { setMessages([]); return }
    if (skipFetchRef.current > 0) { skipFetchRef.current -= 1; return }
    listMessages(conversationId).then(({ messages: msgs }) => setMessages(msgs))
  }, [conversationId])

  // Auto-poll for new messages when not streaming ourselves
  // (e.g. viewing a conversation being written by a delegated agent)
  useEffect(() => {
    if (!conversationId || streaming) return
    // Only poll if the last message is recent (within 2 minutes)
    const lastMsg = messages[messages.length - 1]
    if (!lastMsg) return
    const lastTime = new Date(lastMsg.created_at).getTime()
    const age = Date.now() - lastTime
    if (age > 120_000) return  // Older than 2 min, stop polling

    const timer = setInterval(() => {
      listMessages(conversationId).then(({ messages: msgs }) => {
        if (msgs.length !== messages.length) {
          setMessages(msgs)
        }
      }).catch(() => {})
    }, 3000)
    return () => clearInterval(timer)
  }, [conversationId, streaming, messages.length])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamingText, streaming])

  // Auto-scroll tool panel
  useEffect(() => {
    toolPanelBottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [allToolCalls])

  const sendMessage = useCallback(() => {
    const text = input.trim()
    if (!text || !wsRef.current || streaming) return
    setMessages((prev) => [...prev, {
      id: `temp_${Date.now()}`, conversation_id: conversationId || '',
      role: 'user', content: text, tool_calls: null, tool_call_id: null,
      created_at: new Date().toISOString(), tokens_used: 0, metadata: {},
    }])
    setInput(''); setStreaming(true); streamingTextRef.current = ''
    setStreamingText(''); setError('')
    toolCallMapRef.current.clear(); toolCallOrderRef.current = []; setStreamToolCalls([])
    wsRef.current.send(JSON.stringify({ type: 'message', content: text, conversation_id: conversationId }))
    if (textareaRef.current) textareaRef.current.style.height = 'auto'
  }, [input, conversationId, streaming])

  function getTextContent(msg: Message): string {
    if (typeof msg.content === 'string') return msg.content
    return msg.content.filter((p) => p.type === 'text' && p.text).map((p) => p.text!).join('\n')
  }

  function selectConversation(convId: string) {
    setConversationId(convId)
    setSearchParams(convId ? { conv: convId } : {}, { replace: true })
    setTokenUsage({ totalInput: 0, totalOutput: 0, lastInput: 0, lastOutput: 0 })
    setSidebarOpen(false)
  }

  const resetTokens = { totalInput: 0, totalOutput: 0, lastInput: 0, lastOutput: 0 }

  const isCollapsed = sidebarCollapsed && !sidebarOpen
  function toggleSidebarCollapse() {
    setSidebarCollapsed(prev => {
      const next = !prev
      localStorage.setItem('aegis_sidebar_collapsed', String(next))
      return next
    })
  }

  // Group conversations by date (ChatGPT-style)
  const groupedConversations = useMemo(() => {
    const now = new Date()
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
    const yesterday = new Date(today.getTime() - 86400000)
    const weekAgo = new Date(today.getTime() - 7 * 86400000)

    const groups: { label: string; convs: Conversation[] }[] = [
      { label: 'Today', convs: [] },
      { label: 'Yesterday', convs: [] },
      { label: 'Previous 7 days', convs: [] },
      { label: 'Older', convs: [] },
    ]

    for (const c of conversations) {
      const d = new Date(c.updated_at || c.created_at)
      if (d >= today) groups[0].convs.push(c)
      else if (d >= yesterday) groups[1].convs.push(c)
      else if (d >= weekAgo) groups[2].convs.push(c)
      else groups[3].convs.push(c)
    }
    return groups.filter(g => g.convs.length > 0)
  }, [conversations])

  const navItems: { id: Tab; label: string; icon: React.ReactNode }[] = [
    { id: 'settings', label: 'Settings', icon: <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="2" stroke="currentColor" strokeWidth="1.3"/><path d="M8 1v2M8 13v2M1 8h2M13 8h2M3.05 3.05l1.41 1.41M11.54 11.54l1.41 1.41M3.05 12.95l1.41-1.41M11.54 4.46l1.41-1.41" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/></svg> },
    { id: 'knowledge', label: 'Knowledge', icon: <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M2 2h4l2 2h6v9a1 1 0 01-1 1H3a1 1 0 01-1-1V2z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round"/></svg> },
    { id: 'webhooks', label: 'Webhooks', icon: <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="4" r="2" stroke="currentColor" strokeWidth="1.3"/><circle cx="4" cy="12" r="2" stroke="currentColor" strokeWidth="1.3"/><circle cx="12" cy="12" r="2" stroke="currentColor" strokeWidth="1.3"/><path d="M8 6v2.5L5.5 11M8 8.5l2.5 2.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/></svg> },
    { id: 'schedules', label: 'Schedules', icon: <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="1.3"/><path d="M8 4.5V8l2.5 1.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/></svg> },
  ]

  return (
    <div className="flex h-svh bg-background">
      {/* Mobile overlay */}
      {sidebarOpen && (
        <div className="fixed inset-0 z-30 bg-black/50 md:hidden" onClick={() => setSidebarOpen(false)} />
      )}

      {/* ── Left Sidebar (GPT-style) ── */}
      <div className={`
        fixed inset-y-0 left-0 z-40 flex flex-col bg-sidebar
        transition-all duration-200 ease-in-out
        md:relative md:z-auto md:translate-x-0
        ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'}
      `} style={{ width: sidebarOpen ? 280 : (isCollapsed ? 52 : 260) }}>

        {/* Top row: logo/back + collapse toggle */}
        <div className={`flex items-center shrink-0 ${isCollapsed ? 'flex-col gap-1 py-2' : 'justify-between px-3 py-2.5'}`}>
          <Link to="/" className={`flex items-center gap-2 rounded-lg p-1.5 text-foreground hover:bg-sidebar-accent transition-colors ${isCollapsed ? '' : ''}`} title="Back to Chat">
            <svg width="18" height="18" viewBox="0 0 16 16" fill="none">
              <path d="M2 3a1 1 0 011-1h10a1 1 0 011 1v7a1 1 0 01-1 1H5l-3 3V3z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round"/>
            </svg>
            {!isCollapsed && <span className="text-sm font-semibold">Aegis</span>}
          </Link>
          <div className="flex items-center gap-0.5">
            {!isCollapsed && (
              <button onClick={() => setSidebarOpen(false)} className="rounded-lg p-1.5 text-sidebar-foreground hover:bg-sidebar-accent md:hidden">
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></svg>
              </button>
            )}
            <button onClick={toggleSidebarCollapse}
              className="hidden md:flex rounded-lg p-1.5 text-sidebar-foreground hover:bg-sidebar-accent transition-colors"
              title={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}>
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <rect x="1.5" y="2" width="13" height="12" rx="2" stroke="currentColor" strokeWidth="1.3" />
                <line x1="5.5" y1="2" x2="5.5" y2="14" stroke="currentColor" strokeWidth="1.3" />
              </svg>
            </button>
          </div>
        </div>

        {/* New Chat button */}
        <div className={isCollapsed ? 'flex justify-center px-1 py-1' : 'px-2 pb-1'}>
          <button
            onClick={() => { setActiveTab('chat'); setConversationId(null); setMessages([]); setTokenUsage(resetTokens); setSidebarOpen(false); setSearchParams({}, { replace: true }) }}
            className={isCollapsed
              ? 'rounded-lg p-2 text-sidebar-foreground hover:bg-sidebar-accent transition-colors'
              : 'flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm text-sidebar-foreground hover:bg-sidebar-accent transition-colors'
            }
            title="New Chat">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M8 3v10M3 8h10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
            {!isCollapsed && <span>New chat</span>}
          </button>
        </div>

        {/* Agent config nav — pinned above conversations */}
        <div className={`shrink-0 ${isCollapsed ? 'px-1 py-1' : 'px-2 py-1 border-b border-sidebar-border'}`}>
          {!isCollapsed && (
            <div className="px-3 py-1 text-[11px] font-medium text-sidebar-foreground/50 uppercase tracking-wider">Agent</div>
          )}
          {navItems.map((item) => (
            <button key={item.id}
              onClick={() => { setActiveTab(item.id); setSidebarOpen(false) }}
              className={`flex items-center gap-2.5 rounded-lg transition-colors ${
                isCollapsed
                  ? `justify-center mx-auto my-0.5 p-2 w-10 h-9 ${activeTab === item.id ? 'bg-sidebar-accent text-sidebar-foreground' : 'text-sidebar-foreground/50 hover:bg-sidebar-accent/50 hover:text-sidebar-foreground'}`
                  : `w-full px-3 py-1.5 ${activeTab === item.id ? 'bg-sidebar-accent text-sidebar-foreground' : 'text-sidebar-foreground/70 hover:bg-sidebar-accent/50'}`
              }`}
              title={item.label}>
              <span className="shrink-0 w-4 h-4 flex items-center justify-center">{item.icon}</span>
              {!isCollapsed && <span className="text-sm">{item.label}</span>}
            </button>
          ))}
        </div>

        {/* Scrollable conversation list */}
        <div className="flex-1 overflow-y-auto overflow-x-hidden">
          {!isCollapsed && (
            <div className="px-2 py-1">
              {conversations.length === 0 && (
                <div className="py-8 text-center text-[11px] text-sidebar-foreground/40">No conversations yet</div>
              )}
              {groupedConversations.map((group) => (
                <div key={group.label} className="mb-2">
                  <div className="px-3 py-1.5 text-[11px] font-medium text-sidebar-foreground/50">{group.label}</div>
                  {group.convs.map((conv) => (
                    <button key={conv.id}
                      onClick={() => { selectConversation(conv.id); setActiveTab('chat') }}
                      className={`group flex w-full items-center rounded-lg px-3 py-2 text-left transition-colors ${
                        conversationId === conv.id && activeTab === 'chat'
                          ? 'bg-sidebar-accent text-sidebar-foreground'
                          : 'text-sidebar-foreground/70 hover:bg-sidebar-accent/50'
                      }`}>
                      <span className="flex-1 truncate text-sm">{conv.title}</span>
                      <span
                        onClick={async (e) => {
                          e.stopPropagation()
                          try {
                            await deleteConversation(conv.id)
                            setConversations((prev) => prev.filter((c) => c.id !== conv.id))
                            if (conversationId === conv.id) { setConversationId(null); setMessages([]) }
                          } catch { /* ignore */ }
                        }}
                        className="ml-1 shrink-0 rounded p-0.5 text-sidebar-foreground/20 hover:bg-destructive/20 hover:text-destructive opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer"
                        title="Delete">
                        <svg width="12" height="12" viewBox="0 0 14 14" fill="none">
                          <path d="M3 3l8 8M11 3l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                        </svg>
                      </span>
                    </button>
                  ))}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Bottom: user menu */}
        <div className={`shrink-0 border-t border-sidebar-border ${isCollapsed ? 'py-2 flex justify-center' : 'p-2'}`}>
          <UserMenu collapsed={isCollapsed} />
        </div>
      </div>

      {/* Main + Tool Panel wrapper */}
      <div className="flex flex-1 overflow-hidden">
        {/* Main Content */}
        <main className="flex flex-1 flex-col overflow-hidden">
          {/* Mobile top bar */}
          <div className="flex items-center gap-2 border-b border-border p-2 md:hidden">
            <button onClick={() => setSidebarOpen(true)} className="rounded p-1.5 text-muted-foreground hover:text-foreground">
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                <path d="M3 5h14M3 10h14M3 15h14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
              </svg>
            </button>
            <span className="truncate text-sm font-medium text-foreground">{agent?.name || 'Agent'}</span>
            <span className={`h-2 w-2 rounded-full ${connected ? 'bg-emerald-500' : 'bg-zinc-500'}`} />
            {/* Tool panel toggle (mobile) */}
            {activeTab === 'chat' && (
              <button onClick={() => setToolPanelOpen(!toolPanelOpen)}
                className="ml-auto rounded p-1.5 text-muted-foreground hover:text-foreground relative">
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                  <rect x="1" y="2" width="14" height="12" rx="2" stroke="currentColor" strokeWidth="1.5" />
                  <line x1="10" y1="2" x2="10" y2="14" stroke="currentColor" strokeWidth="1.5" />
                </svg>
                {allToolCalls.length > 0 && (
                  <span className="absolute -top-0.5 -right-0.5 flex h-3.5 w-3.5 items-center justify-center rounded-full bg-primary text-[8px] font-bold text-primary-foreground">
                    {allToolCalls.length}
                  </span>
                )}
              </button>
            )}
          </div>

          {activeTab === 'chat' && (
            <>
              {/* Messages — NO tool calls inline */}
              <div className="flex-1 overflow-y-auto">
                <div className="mx-auto max-w-3xl space-y-4 p-3 pb-8 sm:p-4">
                  {messages.length === 0 && !streamingText && !streaming && (
                    <div className="flex flex-col items-center justify-center py-16 text-center sm:py-24">
                      <div className="text-4xl mb-3 sm:text-5xl sm:mb-4">&#129302;</div>
                      <h3 className="text-base font-medium text-foreground sm:text-lg">{agent?.name || 'Agent'}</h3>
                      <p className="mt-2 max-w-md text-xs text-muted-foreground sm:text-sm">
                        {agent?.system_prompt ? agent.system_prompt.slice(0, 200) + (agent.system_prompt.length > 200 ? '...' : '') : 'Send a message to start chatting'}
                      </p>
                      <p className="mt-3 text-[10px] text-muted-foreground sm:text-xs">{agent?.model}</p>
                    </div>
                  )}

                  {messages.map((msg) => {
                    const text = getTextContent(msg)
                    const isUser = msg.role === 'user'

                    // Skip tool result messages (shown in right panel)
                    if (msg.role === 'tool') return null

                    if (isUser) {
                      if (!text) return null
                      return (
                        <div key={msg.id} className="flex justify-end">
                          <div className="max-w-[90%] rounded-2xl bg-primary px-4 py-3 text-[15px] leading-relaxed text-primary-foreground sm:max-w-[80%]">
                            <div className="whitespace-pre-wrap break-words">{text}</div>
                          </div>
                        </div>
                      )
                    }

                    // Assistant: text only (tool calls are in the right panel)
                    if (!text) return null
                    return (
                      <div key={msg.id} className="flex justify-start">
                        <div className="max-w-[90%] sm:max-w-[85%] text-[15px] leading-relaxed text-foreground agent-message">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
                        </div>
                      </div>
                    )
                  })}

                  {/* Thinking indicator */}
                  {streaming && !streamingText && streamToolCalls.length === 0 && (
                    <div className="flex justify-start">
                      <div className="flex items-center gap-2 rounded-2xl bg-muted px-4 py-3 text-sm text-muted-foreground">
                        <span className="h-3 w-3 rounded-full border-2 border-primary border-t-transparent animate-spin" />
                        <span>Thinking...</span>
                      </div>
                    </div>
                  )}

                  {/* Using tools indicator (when tools are running but no text yet) */}
                  {streaming && !streamingText && streamToolCalls.length > 0 && (
                    <div className="flex justify-start">
                      <div className="flex items-center gap-2 rounded-2xl bg-muted px-3 py-2.5 text-sm text-muted-foreground sm:px-4 sm:py-3">
                        <span className="h-3 w-3 rounded-full border-2 border-primary border-t-transparent animate-spin" />
                        Using tools...
                      </div>
                    </div>
                  )}

                  {/* Streaming text */}
                  {streamingText && (
                    <div className="flex justify-start">
                      <div className="max-w-[90%] text-[15px] leading-relaxed text-foreground sm:max-w-[85%] agent-message">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{streamingText}</ReactMarkdown>
                        <span className="inline-block h-4 w-0.5 animate-pulse bg-foreground/50 ml-0.5" />
                      </div>
                    </div>
                  )}

                  {/* MCP Auth banner */}
                  {mcpAuthRequest && (
                    <div className="rounded-lg border border-yellow-500/30 bg-yellow-500/10 p-4 text-sm">
                      <div className="flex items-center gap-2 mb-2">
                        <span className="text-yellow-500 text-base">🔐</span>
                        <span className="font-medium text-yellow-200">Authentication Required</span>
                        <span className="text-xs text-muted-foreground">— {mcpAuthRequest.serverId}</span>
                      </div>
                      {mcpAuthRequest.deviceCode ? (
                        <>
                          <p className="text-xs text-muted-foreground mb-3">Open the link below and enter this code to sign in:</p>
                          <div className="flex items-center gap-3 mb-3">
                            <code className="rounded bg-background px-3 py-2 text-lg font-bold tracking-widest text-foreground">{mcpAuthRequest.deviceCode}</code>
                            <button onClick={() => { navigator.clipboard.writeText(mcpAuthRequest.deviceCode!) }}
                              className="text-xs text-muted-foreground hover:text-foreground">Copy</button>
                          </div>
                        </>
                      ) : (
                        <p className="text-xs text-muted-foreground mb-2 font-mono whitespace-pre-wrap">{mcpAuthRequest.message}</p>
                      )}
                      <div className="flex items-center gap-2">
                        {mcpAuthRequest.authUrl && (
                          <a href={mcpAuthRequest.authUrl} target="_blank" rel="noopener noreferrer"
                            className="rounded-md bg-yellow-500/20 px-3 py-1.5 text-xs font-medium text-yellow-200 hover:bg-yellow-500/30 transition-colors inline-block">
                            Open Sign-In Page ↗
                          </a>
                        )}
                        <button onClick={() => setMcpAuthRequest(null)} className="text-xs text-muted-foreground hover:text-foreground">Dismiss</button>
                      </div>
                    </div>
                  )}

                  {error && (
                    <div className="rounded-md bg-destructive/10 p-3 text-center text-sm text-destructive">{error}</div>
                  )}
                  <div ref={bottomRef} />
                </div>
              </div>

              {/* Input area */}
              <div className="border-t border-border bg-background">
                {tokenUsage.totalInput + tokenUsage.totalOutput > 0 && (
                  <div className="mx-auto flex max-w-3xl items-center justify-between px-3 pt-1.5 text-[10px] text-muted-foreground sm:px-4 sm:pt-2 sm:text-[11px]">
                    <span>Last: {tokenUsage.lastInput + tokenUsage.lastOutput} tokens</span>
                    <span>Session: {(tokenUsage.totalInput + tokenUsage.totalOutput).toLocaleString()}</span>
                  </div>
                )}
                <form onSubmit={(e) => { e.preventDefault(); sendMessage() }} className="mx-auto max-w-3xl px-3 pb-3 pt-1.5 sm:px-4 sm:pb-4 sm:pt-2">
                  <div className="flex items-end gap-2 rounded-xl border border-border bg-muted p-2 sm:p-3">
                    <textarea
                      ref={textareaRef}
                      value={input}
                      onChange={(e) => setInput(e.target.value)}
                      onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); if (!streaming) sendMessage() } }}
                      placeholder={connected ? (streaming ? 'Wait for response or stop...' : 'Type a message...') : 'Connecting...'}
                      disabled={!connected}
                      rows={1}
                      className="flex-1 resize-none border-0 bg-transparent px-2 py-1.5 text-[15px] leading-relaxed text-foreground placeholder:text-muted-foreground focus:outline-none"
                      style={{ maxHeight: '200px' }}
                    />
                    {/* Tool panel toggle button (desktop) */}
                    <button type="button" onClick={() => setToolPanelOpen(!toolPanelOpen)}
                      className={`hidden md:flex h-9 w-9 shrink-0 items-center justify-center rounded-md transition-colors relative ${
                        toolPanelOpen ? 'bg-primary/20 text-primary' : 'text-muted-foreground hover:text-foreground'
                      }`}
                      title={toolPanelOpen ? 'Hide tool panel' : 'Show tool panel'}>
                      <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                        <rect x="1" y="2" width="14" height="12" rx="2" stroke="currentColor" strokeWidth="1.5" />
                        <line x1="10" y1="2" x2="10" y2="14" stroke="currentColor" strokeWidth="1.5" />
                      </svg>
                      {allToolCalls.length > 0 && (
                        <span className="absolute -top-1 -right-1 flex h-4 w-4 items-center justify-center rounded-full bg-primary text-[9px] font-bold text-primary-foreground">
                          {allToolCalls.length > 99 ? '99+' : allToolCalls.length}
                        </span>
                      )}
                    </button>
                    {streaming ? (
                      <button type="button" onClick={() => { wsRef.current?.send(JSON.stringify({ type: 'cancel' })); setStreaming(false); streamingTextRef.current = ''; setStreamingText('') }}
                        className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-foreground p-0 transition-colors hover:bg-foreground/80"
                        title="Stop generating">
                        <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                          <rect x="1" y="1" width="10" height="10" rx="1" fill="var(--color-background)" />
                        </svg>
                      </button>
                    ) : (
                      <Button type="submit" size="sm" disabled={!input.trim() || !connected}
                        className="h-9 w-9 shrink-0 p-0 sm:h-9 sm:w-auto sm:px-3">
                        <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                          <path d="M14 2L7 9M14 2l-4 12-3-5-5-3 12-4z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                      </Button>
                    )}
                  </div>
                </form>
              </div>
            </>
          )}

          {activeTab === 'settings' && agent && (
            <div className="flex-1 overflow-y-auto">
              <AgentSettingsPanel agent={agent} onUpdate={setAgent} />
            </div>
          )}

          {activeTab === 'webhooks' && agentId && (
            <div className="flex-1 overflow-y-auto">
              <WebhooksPanel agentId={agentId} />
            </div>
          )}

          {activeTab === 'schedules' && agentId && (
            <div className="flex-1 overflow-y-auto">
              <SchedulesPanel agentId={agentId} />
            </div>
          )}

          {activeTab === 'knowledge' && agentId && (
            <div className="flex-1 overflow-y-auto">
              <KnowledgePanel agentId={agentId} />
            </div>
          )}
        </main>

        {/* Mobile tool panel overlay */}
        {activeTab === 'chat' && toolPanelOpen && (
          <div className="fixed inset-0 z-30 bg-black/50 md:hidden" onClick={() => setToolPanelOpen(false)} />
        )}

        {/* Right Tool Panel — slides in on mobile, inline on desktop */}
        {activeTab === 'chat' && toolPanelOpen && (
          <aside className={`
            fixed inset-y-0 right-0 z-40 flex w-80 flex-col border-l border-border bg-sidebar transition-transform duration-200
            md:relative md:z-auto md:translate-x-0
          `}>
            <div className="flex items-center justify-between border-b border-border px-4 py-3">
              <div className="flex items-center gap-2">
                <svg width="14" height="14" viewBox="0 0 16 16" fill="none" className="text-muted-foreground">
                  <path d="M8 1v4M8 11v4M1 8h4M11 8h4M3.5 3.5l2.5 2.5M10 10l2.5 2.5M3.5 12.5L6 10M10 6l2.5-2.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                </svg>
                <span className="text-sm font-medium text-foreground">Tool Activity</span>
                {allToolCalls.length > 0 && (
                  <span className="rounded-full bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
                    {allToolCalls.length}
                  </span>
                )}
              </div>
              <button onClick={() => setToolPanelOpen(false)} className="rounded p-1 text-muted-foreground hover:text-foreground">
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                  <path d="M3 3l8 8M11 3l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                </svg>
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-3 space-y-1">
              {allToolCalls.length === 0 && (
                <div className="flex flex-col items-center justify-center py-12 text-center">
                  <svg width="24" height="24" viewBox="0 0 16 16" fill="none" className="text-muted-foreground/30 mb-2">
                    <path d="M8 1v4M8 11v4M1 8h4M11 8h4M3.5 3.5l2.5 2.5M10 10l2.5 2.5M3.5 12.5L6 10M10 6l2.5-2.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                  </svg>
                  <p className="text-xs text-muted-foreground">No tool calls yet</p>
                  <p className="text-[10px] text-muted-foreground/60 mt-1">Tool activity will appear here</p>
                </div>
              )}
              {allToolCalls.map((tc) => (
                <ToolCallBlock key={tc.id} tool={tc} />
              ))}
              <div ref={toolPanelBottomRef} />
            </div>
          </aside>
        )}
      </div>
    </div>
  )
}
