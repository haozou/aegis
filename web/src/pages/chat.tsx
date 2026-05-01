import { useEffect, useState, useRef, useCallback, useMemo } from 'react'
import { createPortal } from 'react-dom'
import { useNavigate, useSearchParams, Link } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { UserMenu } from '@/components/user-menu'
import { listAgents, updateAgent } from '@/api/agents'
import { listModels } from '@/api/models'
import { listConversations, listMessages, deleteConversation } from '@/api/conversations'
import { getAccessToken } from '@/api/client'
import { uploadFile } from '@/api/files'
import { ToolCallBlock } from '@/components/agent/tool-call-block'
import { ArtifactsPanel, type Artifact } from '@/components/artifacts-panel'
import type { Agent, Conversation, Message, StreamEvent, WsMessage, ToolCall } from '@/types'

const SELECTED_AGENT_KEY = 'aegis_selected_agent'
const SIDEBAR_COLLAPSED_KEY = 'aegis_sidebar_collapsed'

const ALL_TOOLS = [
  { id: 'web_search', name: 'Web Search' }, { id: 'web_fetch', name: 'Web Fetch' },
  { id: 'bash', name: 'Bash Shell' }, { id: 'file_read', name: 'File Read' },
  { id: 'file_write', name: 'File Write' }, { id: 'file_list', name: 'File List' },
  { id: 'manage_schedules', name: 'Schedules' }, { id: 'knowledge_base', name: 'Knowledge' },
  { id: 'delegate_to_agent', name: 'Delegate' }, { id: 'video_probe', name: 'Video Probe' },
  { id: 'video_cut', name: 'Video Cut' }, { id: 'video_concat', name: 'Video Concat' },
  { id: 'video_add_audio', name: 'Add Audio' }, { id: 'video_thumbnail', name: 'Thumbnail' },
  { id: 'video_export', name: 'Video Export' }, { id: 'video_overlay_text', name: 'Overlay Text' },
  { id: 'video_speed', name: 'Video Speed' }, { id: 'image_generate', name: 'Image Gen' },
  { id: 'file_export', name: 'File Export' },
  { id: 'python', name: 'Python' },
]

interface AttachmentPreview {
  /** undefined while uploading */
  file_id?: string
  filename: string
  media_type: string
  /** object URL for image preview */
  objectUrl?: string
  uploading: boolean
  /** local key for React list */
  key: string
}

export function ChatPage() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()

  // Agents
  const [agents, setAgents] = useState<Agent[]>([])
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(() => localStorage.getItem(SELECTED_AGENT_KEY))
  const [agentDropdownOpen, setAgentDropdownOpen] = useState(false)
  const [modelDropdownOpen, setModelDropdownOpen] = useState(false)
  const [toolsDropdownOpen, setToolsDropdownOpen] = useState(false)
  const [availableModels, setAvailableModels] = useState<string[]>([])

  // Conversations
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [conversationId, setConversationId] = useState<string | null>(searchParams.get('conv'))

  // Messages & chat
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [quotedRef, setQuotedRef] = useState<{ author: string; text: string } | null>(null)
  const [streaming, setStreaming] = useState(false)
  const [streamingText, setStreamingText] = useState('')
  const [connected, setConnected] = useState(false)
  const [error, setError] = useState('')
  const [tokenUsage, setTokenUsage] = useState({ totalInput: 0, totalOutput: 0, lastInput: 0, lastOutput: 0 })

  // Tool calls
  const [streamToolCalls, setStreamToolCalls] = useState<ToolCall[]>([])
  const [toolPanelOpen, setToolPanelOpen] = useState(() => window.innerWidth >= 768)
  const [rightTab, setRightTab] = useState<'tools' | 'artifacts'>('tools')
  const [activeArtifact, setActiveArtifact] = useState<Artifact | null>(null)

  // Attachments
  const [attachments, setAttachments] = useState<AttachmentPreview[]>([])
  const fileInputRef = useRef<HTMLInputElement>(null)

  // MCP auth
  const [mcpAuthRequest, setMcpAuthRequest] = useState<{
    serverId: string; message: string; authUrl?: string; deviceCode?: string
  } | null>(null)

  // Sidebar
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === 'true')
  const [sidebarOpen, setSidebarOpen] = useState(false)

  // Conversation search / filter / sort
  const [convSearch, setConvSearch] = useState('')
  const [convAgentFilter, setConvAgentFilter] = useState<string>('all')
  const [convSort, setConvSort] = useState<'recent' | 'oldest' | 'az'>('recent')

  const wsRef = useRef<WebSocket | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const toolPanelBottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const streamingTextRef = useRef('')
  const lastStreamEndRef = useRef(0) // timestamp when last stream finished
  const skipFetchRef = useRef(0)
  const toolCallMapRef = useRef<Map<string, ToolCall>>(new Map())
  const toolCallOrderRef = useRef<string[]>([])
  const agentBtnRef = useRef<HTMLButtonElement>(null)
  const modelBtnRef = useRef<HTMLButtonElement>(null)
  const toolsBtnRef = useRef<HTMLButtonElement>(null)

  /** Get rect for positioning a portal dropdown above a button ref */
  function getDropdownStyle(ref: React.RefObject<HTMLButtonElement | null>): React.CSSProperties {
    if (!ref.current) return {}
    const r = ref.current.getBoundingClientRect()
    return { position: 'fixed', bottom: window.innerHeight - r.top + 6, left: r.left, zIndex: 9999 }
  }

  // Compute all tool calls from messages + streaming for the right panel
  const allToolCalls = useMemo(() => {
    const toolOutputs: Record<string, string> = {}
    for (const msg of messages) {
      if (msg.role === 'tool' && msg.tool_call_id) {
        toolOutputs[msg.tool_call_id] = getTextContent(msg)
      }
    }
    const fromMessages: ToolCall[] = []
    for (const msg of messages) {
      if (msg.role === 'assistant' && msg.tool_calls) {
        for (const tc of msg.tool_calls as ToolCall[]) {
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

  const selectedAgent = useMemo(() => agents.find(a => a.id === selectedAgentId) ?? null, [agents, selectedAgentId])
  const activeAgents = useMemo(() => agents.filter(a => a.status === 'active'), [agents])

  function autoResize() {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 200) + 'px'
  }

  useEffect(() => { autoResize() }, [input])

  // Load agents on mount
  useEffect(() => {
    listAgents()
      .then(({ agents: list }) => {
        setAgents(list)
        // Auto-select: try saved agent, fall back to first active
        const saved = localStorage.getItem(SELECTED_AGENT_KEY)
        const found = saved ? list.find(a => a.id === saved) : null
        if (!found) {
          const first = list.find(a => a.status === 'active') ?? list[0]
          if (first) {
            setSelectedAgentId(first.id)
            localStorage.setItem(SELECTED_AGENT_KEY, first.id)
          }
        }
      })
      .catch(() => navigate('/login'))
  }, [navigate])

  // Load all conversations on mount
  useEffect(() => {
    listConversations()
      .then(({ conversations: convs }) => setConversations(convs))
      .catch(() => {})
  }, [])

  useEffect(() => {
    listModels().then(({ models }) => setAvailableModels(models)).catch(() => {})
  }, [])

  function updateAgentLocal(patch: Partial<Agent>) {
    if (!selectedAgentId) return
    updateAgent(selectedAgentId, patch).then(({ agent: updated }) => {
      setAgents(prev => prev.map(a => a.id === updated.id ? updated : a))
    }).catch(() => {})
  }

  function syncToolCallsToState() {
    const ordered = toolCallOrderRef.current.map(id => toolCallMapRef.current.get(id)!).filter(Boolean)
    setStreamToolCalls([...ordered])
  }

  // Connect WebSocket — reconnects when selectedAgentId changes, auto-reconnects on disconnect
  useEffect(() => {
    if (!selectedAgentId) return
    const token = getAccessToken()
    if (!token) { navigate('/login'); return }

    let reconnectAttempt = 0
    let reconnectTimer: number | null = null
    let pingTimer: number | null = null
    let cancelled = false
    let currentWs: WebSocket | null = null

    const connect = () => {
      if (cancelled) return
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const ws = new WebSocket(`${protocol}//${window.location.host}/ws/agents/${selectedAgentId}/chat`)
      wsRef.current = ws
      currentWs = ws
      setConnected(false)

      ws.onopen = () => {
        ws.send(JSON.stringify({ type: 'auth', token }))
        reconnectAttempt = 0
        // Heartbeat every 30s to keep Cloudflare / proxies from timing out
        if (pingTimer) window.clearInterval(pingTimer)
        pingTimer = window.setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            try { ws.send(JSON.stringify({ type: 'ping' })) } catch { /* ignore */ }
          }
        }, 30000)
      }

    ws.onmessage = (event) => {
        const data: WsMessage = JSON.parse(event.data)
        switch (data.type) {
          case 'auth_ok':
            setConnected(true); setError('')
            {
              const convFromUrl = new URLSearchParams(window.location.search).get('conv')
              if (convFromUrl) {
                listMessages(convFromUrl).then(({ messages: msgs }) => setMessages(msgs)).catch(() => {})
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
              provider: selectedAgent?.provider || 'anthropic', model: selectedAgent?.model || '',
              system_prompt: null, user_id: null, agent_id: selectedAgentId!, metadata: {},
            }, ...prev])
            break
          }
          case 'tool_start': {
            setStreaming(true)
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
            setStreaming(true)
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
            lastStreamEndRef.current = Date.now()
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

      ws.onclose = () => {
        setConnected(false)
        if (pingTimer) { window.clearInterval(pingTimer); pingTimer = null }
        if (cancelled) return
        // Exponential backoff: 1s, 2s, 4s, 8s, ... capped at 30s
        const delay = Math.min(1000 * Math.pow(2, reconnectAttempt), 30000)
        reconnectAttempt += 1
        reconnectTimer = window.setTimeout(connect, delay)
      }
      ws.onerror = () => { setError('WebSocket connection failed'); setConnected(false) }
    }

    connect()

    return () => {
      cancelled = true
      if (reconnectTimer) window.clearTimeout(reconnectTimer)
      if (pingTimer) window.clearInterval(pingTimer)
      if (currentWs) currentWs.close()
      wsRef.current = null
    }
  }, [selectedAgentId, navigate])

  useEffect(() => {
    if (!conversationId) { setMessages([]); return }
    if (skipFetchRef.current > 0) { skipFetchRef.current -= 1; return }
    listMessages(conversationId)
      .then(({ messages: msgs }) => setMessages(msgs))
      .catch(() => setMessages([]))  // 404 or error — clear instead of showing stale messages
  }, [conversationId])

  // Auto-poll for new messages when not streaming
  useEffect(() => {
    if (!conversationId || streaming) return
    const lastMsg = messages[messages.length - 1]
    if (!lastMsg) return
    const age = Date.now() - new Date(lastMsg.created_at).getTime()
    if (age > 120_000) return
    const timer = setInterval(() => {
      listMessages(conversationId).then(({ messages: msgs }) => {
        if (msgs.length !== messages.length) setMessages(msgs)
      }).catch(() => {})
    }, 3000)
    return () => clearInterval(timer)
  }, [conversationId, streaming, messages.length])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamingText, streaming])

  useEffect(() => {
    toolPanelBottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [allToolCalls])

  // Close agent dropdown on outside click
  useEffect(() => {
    if (!agentDropdownOpen) return
    function handleClick() { setAgentDropdownOpen(false) }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [agentDropdownOpen])

  useEffect(() => {
    if (!modelDropdownOpen) return
    function handleClick() { setModelDropdownOpen(false) }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [modelDropdownOpen])

  useEffect(() => {
    if (!toolsDropdownOpen) return
    function handleClick() { setToolsDropdownOpen(false) }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [toolsDropdownOpen])

  const sendMessage = useCallback(() => {
    const text = input.trim()
    const readyAttachments = attachments.filter(a => !a.uploading && a.file_id)
    if ((!text && readyAttachments.length === 0) || !wsRef.current || streaming) return
    // Send quote as a separate field — server stores it in metadata.quote and prepends
    // for the LLM. The chat bubble shows ONLY `text`, with the quote rendered as a pill above.
    const meta: Record<string, any> = {}
    if (readyAttachments.length > 0) {
      meta.attachments = readyAttachments.map(a => ({ file_id: a.file_id!, filename: a.filename, media_type: a.media_type }))
    }
    if (quotedRef) {
      meta.quote = { author: quotedRef.author, text: quotedRef.text }
    }
    setMessages((prev) => [...prev, {
      id: `temp_${Date.now()}`, conversation_id: conversationId || '',
      role: 'user', content: text, tool_calls: null, tool_call_id: null,
      created_at: new Date().toISOString(), tokens_used: 0,
      metadata: meta,
    }])
    setInput(''); setStreaming(true); streamingTextRef.current = ''
    setStreamingText(''); setError('')
    toolCallMapRef.current.clear(); toolCallOrderRef.current = []; setStreamToolCalls([])
    // Clean up object URLs and clear attachments
    attachments.forEach(a => a.objectUrl && URL.revokeObjectURL(a.objectUrl))
    setAttachments([])
    wsRef.current.send(JSON.stringify({
      type: 'message',
      content: text,
      conversation_id: conversationId,
      attachments: readyAttachments.map(({ file_id, filename, media_type }) => ({ file_id, filename, media_type })),
      quote: quotedRef ? { author: quotedRef.author, text: quotedRef.text } : null,
    }))
    setQuotedRef(null)
    if (textareaRef.current) textareaRef.current.style.height = 'auto'
  }, [input, attachments, conversationId, streaming, quotedRef])

  function getTextContent(msg: Message): string {
    if (typeof msg.content === 'string') return msg.content
    return msg.content.filter((p) => p.type === 'text' && p.text).map((p) => p.text!).join('\n')
  }

  function removeAttachment(key: string) {
    setAttachments(prev => {
      const att = prev.find(a => a.key === key)
      if (att?.objectUrl) URL.revokeObjectURL(att.objectUrl)
      return prev.filter(a => a.key !== key)
    })
  }

  async function handleFileSelect(file: File) {
    const key = `${Date.now()}_${Math.random()}`
    const isImage = file.type.startsWith('image/')
    // Create objectUrl immediately — on Android, the File reference can become stale after async
    const objectUrl = isImage ? URL.createObjectURL(file) : undefined
    setAttachments(prev => [...prev, {
      key,
      filename: file.name || 'upload',
      media_type: file.type || 'application/octet-stream',
      objectUrl,
      uploading: true,
    }])
    try {
      const result = await uploadFile(file)
      setAttachments(prev => prev.map(a => a.key === key
        ? { ...a, file_id: result.file_id, uploading: false }
        : a
      ))
    } catch (err) {
      console.error('File upload failed:', err)
      // Keep the preview but mark as failed so user can see something went wrong
      setAttachments(prev => prev.filter(a => a.key !== key))
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }

  function selectConversation(conv: Conversation) {
    // Auto-switch to that conversation's agent
    if (conv.agent_id && conv.agent_id !== selectedAgentId) {
      setSelectedAgentId(conv.agent_id)
      localStorage.setItem(SELECTED_AGENT_KEY, conv.agent_id)
    }
    setConversationId(conv.id)
    setSearchParams({ conv: conv.id }, { replace: true })
    setTokenUsage({ totalInput: 0, totalOutput: 0, lastInput: 0, lastOutput: 0 })
    setSidebarOpen(false)
  }

  function selectAgent(agentId: string, startNew = true) {
    setSelectedAgentId(agentId)
    localStorage.setItem(SELECTED_AGENT_KEY, agentId)
    if (startNew) {
      setConversationId(null)
      setMessages([])
      setTokenUsage({ totalInput: 0, totalOutput: 0, lastInput: 0, lastOutput: 0 })
      setSearchParams({}, { replace: true })
      setSidebarOpen(false)
    }
    setAgentDropdownOpen(false)
  }

  function startNewChat() {
    setConversationId(null)
    setMessages([])
    setTokenUsage({ totalInput: 0, totalOutput: 0, lastInput: 0, lastOutput: 0 })
    setSearchParams({}, { replace: true })
    setSidebarOpen(false)
  }

  const isCollapsed = sidebarCollapsed && !sidebarOpen

  function toggleSidebarCollapse() {
    setSidebarCollapsed(prev => {
      const next = !prev
      localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(next))
      return next
    })
  }

  const [copiedMsgId, setCopiedMsgId] = useState<string | null>(null)
  const [thumbedMsgId, setThumbedMsgId] = useState<Record<string, 'up' | 'down'>>({})
  const [editingMsgId, setEditingMsgId] = useState<string | null>(null)
  const [editingText, setEditingText] = useState('')

  function copyMessage(id: string, text: string) {
    navigator.clipboard.writeText(text).then(() => {
      setCopiedMsgId(id)
      setTimeout(() => setCopiedMsgId(null), 1500)
    })
  }

  function quoteMessage(text: string, author: string) {
    setQuotedRef({ author, text })
    setTimeout(() => {
      const el = textareaRef.current
      if (el) {
        el.focus()
        el.scrollIntoView({ block: 'end', behavior: 'smooth' })
      }
    }, 50)
  }

  function thumbMessage(id: string, dir: 'up' | 'down') {
    setThumbedMsgId(prev => prev[id] === dir ? { ...prev, [id]: undefined as unknown as 'up' | 'down' } : { ...prev, [id]: dir })
  }

  function regenerateFrom(msg: Message) {
    // Find the last user message before this assistant message
    const idx = messages.findIndex(m => m.id === msg.id)
    const userMsg = [...messages].slice(0, idx).reverse().find(m => m.role === 'user')
    if (!userMsg || !wsRef.current) return
    const text = getTextContent(userMsg)
    if (!text) return
    setMessages(prev => prev.slice(0, idx))
    setStreaming(true)
    streamingTextRef.current = ''
    setStreamingText('')
    setError('')
    toolCallMapRef.current.clear()
    toolCallOrderRef.current = []
    setStreamToolCalls([])
    wsRef.current.send(JSON.stringify({
      type: 'message',
      content: text,
      conversation_id: conversationId,
    }))
  }

  // Group conversations by date
  const filteredGroupedConversations = useMemo(() => {
    let list = conversations

    // Filter by agent
    if (convAgentFilter !== 'all') {
      list = list.filter(c => c.agent_id === convAgentFilter)
    }

    // Search by title
    const q = convSearch.trim().toLowerCase()
    if (q) {
      list = list.filter(c => c.title?.toLowerCase().includes(q))
    }

    // Sort
    list = [...list].sort((a, b) => {
      if (convSort === 'az') return (a.title ?? '').localeCompare(b.title ?? '')
      const aTime = new Date(a.updated_at || a.created_at).getTime()
      const bTime = new Date(b.updated_at || b.created_at).getTime()
      return convSort === 'oldest' ? aTime - bTime : bTime - aTime
    })

    // Flat list when any filter/sort is active
    const isFiltered = convAgentFilter !== 'all' || q || convSort !== 'recent'
    if (isFiltered) {
      return [{ label: null as string | null, convs: list }]
    }

    // Default: date grouping
    const now = new Date()
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
    const yesterday = new Date(today.getTime() - 86400000)
    const weekAgo = new Date(today.getTime() - 7 * 86400000)
    const groups: { label: string | null; convs: Conversation[] }[] = [
      { label: 'Today', convs: [] },
      { label: 'Yesterday', convs: [] },
      { label: 'Previous 7 days', convs: [] },
      { label: 'Older', convs: [] },
    ]
    for (const c of list) {
      const d = new Date(c.updated_at || c.created_at)
      if (d >= today) groups[0].convs.push(c)
      else if (d >= yesterday) groups[1].convs.push(c)
      else if (d >= weekAgo) groups[2].convs.push(c)
      else groups[3].convs.push(c)
    }
    return groups.filter(g => g.convs.length > 0)
  }, [conversations, convSearch, convAgentFilter, convSort])

  const agentName = (agentId: string | null | undefined) =>
    agentId ? (agents.find(a => a.id === agentId)?.name ?? null) : null

  // Markdown components that append auth token to /api/files/ URLs for downloads
  const mdComponents = useMemo(() => {
    const addToken = (url: string) => {
      if (url.startsWith('/api/files/')) {
        const token = getAccessToken()
        return token ? `${url}?token=${token}` : url
      }
      return url
    }
    return {
      a: ({ href, children, ...props }: any) => {
        const url = href || ''
        const isFile = url.startsWith('/api/files/')
        const isImage = /\.(png|jpe?g|gif|webp|svg|bmp)(\?|$)/i.test(url)
        if (isFile && isImage) {
          const tokenized = addToken(url)
          return (
            <a href={tokenized} target="_blank" rel="noopener noreferrer" className="block my-2 not-prose">
              <img
                src={tokenized}
                alt={typeof children === 'string' ? children : 'image'}
                className="max-h-96 max-w-full rounded-md border border-border bg-muted/30 object-contain cursor-zoom-in"
              />
            </a>
          )
        }
        return (
          <a href={addToken(url)} target={isFile ? '_blank' : undefined} rel="noopener noreferrer" {...props}>{children}</a>
        )
      },
      img: ({ src, ...props }: any) => (
        <img src={addToken(src || '')} className="max-h-96 max-w-full rounded-md border border-border my-2" {...props} />
      ),
    }
  }, [])

  // Extract artifacts (large code blocks + /api/files/ links) from assistant text
  function extractArtifacts(text: string, msgId: string): Artifact[] {
    const arts: Artifact[] = []
    // Fenced code blocks
    const codeRe = /```(\w+)?\n([\s\S]*?)```/g
    let m: RegExpExecArray | null
    let idx = 0
    while ((m = codeRe.exec(text))) {
      const lang = m[1] || 'text'
      const content = m[2]
      const lines = content.split('\n').length
      if (lines >= 20) {
        const isHtml = lang === 'html' || /^<!DOCTYPE|^<html/i.test(content.trim())
        arts.push({
          id: `${msgId}-code-${idx}`,
          type: isHtml ? 'html' : 'code',
          title: isHtml ? 'HTML document' : `${lang} (${lines} lines)`,
          language: lang,
          content,
        })
        idx++
      }
    }
    // /api/files/ download links  — e.g. [resume.pdf](/api/files/abc)
    const linkRe = /\[([^\]]+)\]\((\/api\/files\/[^\s)]+)\)/g
    while ((m = linkRe.exec(text))) {
      const filename = m[1]
      const url = m[2].replace(/\?.*$/, '')
      arts.push({
        id: `${msgId}-file-${idx}`,
        type: 'file',
        title: filename,
        filename,
        url,
      })
      idx++
    }
    return arts
  }

  function openArtifact(a: Artifact) {
    setActiveArtifact(a)
    setRightTab('artifacts')
    setToolPanelOpen(true)
  }

  return (
    <div className="flex h-svh bg-background">
      {/* Mobile overlay */}
      {sidebarOpen && (
        <div className="fixed inset-0 z-30 bg-black/50 md:hidden" onClick={() => setSidebarOpen(false)} />
      )}

      {/* ── Left Sidebar ── */}
      <div
        className={`
          fixed inset-y-0 left-0 z-40 flex flex-col bg-sidebar border-r border-sidebar-border w-[280px]
          transition-transform duration-200 ease-in-out
          md:relative md:z-auto md:translate-x-0
          ${sidebarOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'}
          ${isCollapsed ? 'md:w-[52px]' : 'md:w-[260px]'}
        `}
      >
        {/* Top row: logo + controls */}
        <div className={`flex items-center shrink-0 ${isCollapsed ? 'flex-col gap-1 py-3' : 'justify-between px-3 py-3'}`}>
          <div className="flex items-center gap-2.5 px-1">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary/15">
              <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                <path d="M2 3a1 1 0 011-1h10a1 1 0 011 1v7a1 1 0 01-1 1H5l-3 3V3z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" className="text-primary"/>
              </svg>
            </div>
            {!isCollapsed && <span className="text-sm font-bold tracking-tight text-sidebar-foreground">Aegis</span>}
          </div>
          <div className="flex items-center gap-0.5">
            {!isCollapsed && (
              <button onClick={() => setSidebarOpen(false)} className="rounded-lg p-1.5 text-sidebar-foreground/50 hover:bg-sidebar-accent hover:text-sidebar-foreground md:hidden transition-colors">
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></svg>
              </button>
            )}
            <button
              onClick={toggleSidebarCollapse}
              className="hidden md:flex rounded-lg p-1.5 text-sidebar-foreground/40 hover:bg-sidebar-accent hover:text-sidebar-foreground transition-colors"
              title={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            >
              <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
                <rect x="1.5" y="2" width="13" height="12" rx="2" stroke="currentColor" strokeWidth="1.3" />
                <line x1="5.5" y1="2" x2="5.5" y2="14" stroke="currentColor" strokeWidth="1.3" />
              </svg>
            </button>
          </div>
        </div>

        {/* New Chat button */}
        <div className={isCollapsed ? 'flex justify-center px-1.5 pb-2' : 'px-3 pb-2'}>
          <button
            onClick={startNewChat}
            className={isCollapsed
              ? 'rounded-lg p-2 text-primary-foreground bg-primary hover:bg-primary/90 transition-colors shadow-sm'
              : 'flex w-full items-center justify-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-primary-foreground bg-primary hover:bg-primary/90 transition-colors shadow-sm'
            }
            title="New Chat"
          >
            <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
              <path d="M8 3v10M3 8h10" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
            </svg>
            {!isCollapsed && <span>New chat</span>}
          </button>
        </div>

        {/* Navigation */}
        <div className={`shrink-0 ${isCollapsed ? 'px-1.5 pb-2' : 'px-2 pb-2'}`}>
          {!isCollapsed && (
            <div className="px-2 pb-1 pt-0.5 text-[10px] font-semibold text-sidebar-foreground/30 uppercase tracking-widest">Navigate</div>
          )}
          {[
            {
              label: 'Dashboard',
              path: '/dashboard',
              icon: <svg width="15" height="15" viewBox="0 0 16 16" fill="none"><rect x="2" y="2" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.3"/><rect x="9" y="2" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.3"/><rect x="2" y="9" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.3"/><rect x="9" y="9" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.3"/></svg>,
            },
            {
              label: 'Channels',
              path: '/channels',
              icon: <svg width="15" height="15" viewBox="0 0 16 16" fill="none"><path d="M2 4a1 1 0 011-1h10a1 1 0 011 1v6a1 1 0 01-1 1H5l-3 3V4z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round"/></svg>,
            },
            {
              label: 'Schedules',
              path: '/schedules',
              icon: <svg width="15" height="15" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="1.3"/><path d="M8 4.5V8l2.5 1.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/></svg>,
            },
            {
              label: 'Webhooks',
              path: '/webhooks',
              icon: <svg width="15" height="15" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="4" r="2" stroke="currentColor" strokeWidth="1.3"/><circle cx="4" cy="12" r="2" stroke="currentColor" strokeWidth="1.3"/><circle cx="12" cy="12" r="2" stroke="currentColor" strokeWidth="1.3"/><path d="M8 6v2.5L5.5 11M8 8.5l2.5 2.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/></svg>,
            },
            {
              label: 'Knowledge',
              path: '/knowledge',
              icon: <svg width="15" height="15" viewBox="0 0 16 16" fill="none"><path d="M2 2h4l2 2h6v9a1 1 0 01-1 1H3a1 1 0 01-1-1V2z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round"/></svg>,
            },
          ].map((item) => (
            <Link
              key={item.label}
              to={item.path}
              className={
                isCollapsed
                  ? 'flex justify-center mx-auto my-0.5 rounded-lg p-2 w-10 h-8 items-center text-sidebar-foreground/50 hover:bg-sidebar-accent hover:text-sidebar-foreground transition-colors'
                  : 'flex w-full items-center gap-2.5 rounded-lg px-2.5 py-[6px] text-[13px] text-sidebar-foreground/60 hover:bg-sidebar-accent hover:text-sidebar-foreground transition-colors'
              }
              title={item.label}
            >
              <span className="shrink-0 w-4 h-4 flex items-center justify-center">{item.icon}</span>
              {!isCollapsed && <span>{item.label}</span>}
            </Link>
          ))}
        </div>

        {/* Divider */}
        <div className="mx-3 border-t border-sidebar-border" />

        {/* Scrollable conversation list */}
        <div className="flex-1 overflow-y-auto overflow-x-hidden">
          {!isCollapsed && (
            <div className="px-2 pt-2">
              {/* Search + filter bar */}
              <div className="px-1 pb-2 space-y-1.5">
                <div className="relative">
                  <svg width="13" height="13" viewBox="0 0 14 14" fill="none"
                    className="absolute left-2.5 top-1/2 -translate-y-1/2 text-sidebar-foreground/30 pointer-events-none">
                    <circle cx="6" cy="6" r="4.5" stroke="currentColor" strokeWidth="1.3"/>
                    <path d="M9.5 9.5l2.5 2.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
                  </svg>
                  <input
                    type="text"
                    placeholder="Search chats..."
                    value={convSearch}
                    onChange={e => setConvSearch(e.target.value)}
                    className="w-full rounded-lg border border-sidebar-border/60 bg-sidebar-accent/30 pl-8 pr-7 py-[7px] text-xs text-sidebar-foreground placeholder:text-sidebar-foreground/30 focus:outline-none focus:border-primary/50 focus:bg-sidebar-accent/50 transition-colors"
                  />
                  {convSearch && (
                    <button
                      onClick={() => setConvSearch('')}
                      className="absolute right-2.5 top-1/2 -translate-y-1/2 text-sidebar-foreground/30 hover:text-sidebar-foreground transition-colors"
                    >
                      <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                        <path d="M2 2l6 6M8 2l-6 6" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
                      </svg>
                    </button>
                  )}
                </div>
                {/* Filter chips */}
                <div className="flex items-center gap-1 flex-wrap">
                  <button
                    onClick={() => setConvAgentFilter(convAgentFilter === 'all' ? 'all' : 'all')}
                    className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium transition-colors ${
                      convAgentFilter === 'all'
                        ? 'bg-primary/15 text-primary'
                        : 'bg-sidebar-accent/50 text-sidebar-foreground/50 hover:text-sidebar-foreground/70'
                    }`}
                  >
                    All
                  </button>
                  {agents.slice(0, 4).map(a => (
                    <button
                      key={a.id}
                      onClick={() => setConvAgentFilter(convAgentFilter === a.id ? 'all' : a.id)}
                      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium transition-colors truncate max-w-[80px] ${
                        convAgentFilter === a.id
                          ? 'bg-primary/15 text-primary'
                          : 'bg-sidebar-accent/50 text-sidebar-foreground/50 hover:text-sidebar-foreground/70'
                      }`}
                    >
                      {a.name}
                    </button>
                  ))}
                  {agents.length > 4 && convAgentFilter !== 'all' && !agents.slice(0, 4).some(a => a.id === convAgentFilter) && (
                    <button
                      className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium bg-primary/15 text-primary truncate max-w-[80px]"
                    >
                      {agents.find(a => a.id === convAgentFilter)?.name}
                    </button>
                  )}
                  {/* Sort toggle */}
                  <button
                    onClick={() => setConvSort(convSort === 'recent' ? 'oldest' : convSort === 'oldest' ? 'az' : 'recent')}
                    className="ml-auto inline-flex items-center gap-0.5 rounded-full px-1.5 py-0.5 text-[10px] text-sidebar-foreground/40 hover:text-sidebar-foreground/60 hover:bg-sidebar-accent/50 transition-colors"
                    title={`Sort: ${convSort === 'recent' ? 'Newest' : convSort === 'oldest' ? 'Oldest' : 'A–Z'}`}
                  >
                    <svg width="10" height="10" viewBox="0 0 12 12" fill="none">
                      <path d="M2 3h8M2 6h5.5M2 9h3" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
                    </svg>
                    {convSort === 'recent' ? 'New' : convSort === 'oldest' ? 'Old' : 'A–Z'}
                  </button>
                </div>
              </div>
              {filteredGroupedConversations.every(g => g.convs.length === 0) && (
                <div className="py-12 text-center">
                  <div className="text-sidebar-foreground/20 mb-1">
                    <svg width="24" height="24" viewBox="0 0 16 16" fill="none" className="mx-auto">
                      <circle cx="6.5" cy="6.5" r="4.5" stroke="currentColor" strokeWidth="1.3"/>
                      <path d="M10 10l3 3" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
                    </svg>
                  </div>
                  <div className="text-[11px] text-sidebar-foreground/30">
                    {convSearch || convAgentFilter !== 'all' ? 'No matching chats' : 'No conversations yet'}
                  </div>
                </div>
              )}
              {filteredGroupedConversations.map((group, gi) => (
                <div key={group.label ?? gi} className="mb-1">
                  {group.label && (
                    <div className="px-2 pt-2 pb-1 text-[10px] font-semibold text-sidebar-foreground/30 uppercase tracking-widest">{group.label}</div>
                  )}
                  {group.convs.map((conv) => {
                    const convAgentName = agentName(conv.agent_id)
                    const isActive = conversationId === conv.id
                    return (
                      <button
                        key={conv.id}
                        onClick={() => selectConversation(conv)}
                        className={`group flex w-full flex-col rounded-lg px-2.5 py-[7px] text-left transition-all duration-150 ${
                          isActive
                            ? 'bg-sidebar-accent text-sidebar-foreground shadow-sm'
                            : 'text-sidebar-foreground/60 hover:bg-sidebar-accent/50 hover:text-sidebar-foreground/80'
                        }`}
                      >
                        <div className="flex items-center w-full gap-1">
                          <span className={`flex-1 truncate text-[13px] ${isActive ? 'font-medium' : ''}`}>{conv.title}</span>
                          <span
                            onClick={async (e) => {
                              e.stopPropagation()
                              try {
                                await deleteConversation(conv.id)
                                setConversations((prev) => prev.filter((c) => c.id !== conv.id))
                                if (conversationId === conv.id) { setConversationId(null); setMessages([]) }
                              } catch { /* ignore */ }
                            }}
                            className="ml-0.5 shrink-0 rounded p-0.5 text-sidebar-foreground/0 group-hover:text-sidebar-foreground/30 hover:!bg-destructive/20 hover:!text-destructive transition-all cursor-pointer"
                            title="Delete"
                          >
                            <svg width="12" height="12" viewBox="0 0 14 14" fill="none">
                              <path d="M3 3l8 8M11 3l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                            </svg>
                          </span>
                        </div>
                        {convAgentName && (
                          <span className="mt-0.5 text-[10px] text-sidebar-foreground/35 truncate">{convAgentName}</span>
                        )}
                      </button>
                    )
                  })}
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
        <main className="flex flex-1 flex-col overflow-hidden">
          {/* Chat header (responsive) */}
          <div className="flex items-center gap-2 border-b border-border bg-background/80 backdrop-blur-sm px-3 py-2.5 sm:px-5">
            <button
              onClick={() => setSidebarOpen(true)}
              className="rounded p-1.5 text-muted-foreground hover:text-foreground md:hidden"
              title="Menu"
            >
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                <path d="M3 5h14M3 10h14M3 15h14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
              </svg>
            </button>
            <div className="flex min-w-0 flex-1 items-center gap-2.5">
              <div className="hidden sm:flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-primary/10 ring-1 ring-primary/15">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" className="text-primary">
                  <path d="M12 2a5 5 0 015 5v1h1a2 2 0 012 2v6a2 2 0 01-2 2H6a2 2 0 01-2-2V10a2 2 0 012-2h1V7a5 5 0 015-5z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/>
                  <circle cx="9" cy="13" r="1" fill="currentColor"/>
                  <circle cx="15" cy="13" r="1" fill="currentColor"/>
                </svg>
              </div>
              <div className="flex min-w-0 flex-1 items-center gap-2">
                <span className="truncate text-sm font-semibold text-foreground">
                  {selectedAgent?.name || 'Select agent'}
                </span>
                {selectedAgent?.model && (
                  <span className="hidden md:inline truncate text-[11px] text-muted-foreground/70 font-mono">
                    {selectedAgent.model}
                  </span>
                )}
              </div>
              {/* Connection status */}
              <span
                className={`flex items-center gap-1.5 shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium ${
                  connected
                    ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                    : 'bg-amber-500/10 text-amber-600 dark:text-amber-400'
                }`}
                title={connected ? 'Connected' : 'Reconnecting...'}
              >
                <span className={`h-1.5 w-1.5 rounded-full ${connected ? 'bg-emerald-500 animate-pulse' : 'bg-amber-500 animate-pulse'}`} />
                <span className="hidden sm:inline">{connected ? 'Live' : 'Connecting'}</span>
              </span>
            </div>
            <div className="flex items-center gap-0.5">
              {/* New chat */}
              <button
                onClick={startNewChat}
                className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
                title="New chat"
              >
                <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
                  <path d="M2 3h7M2 6h4M2 9h4" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
                  <path d="M11 9v4M9 11h4" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
                </svg>
              </button>
              {/* Export chat */}
              <button
                onClick={() => {
                  const md = messages.map(m => {
                    const role = m.role === 'user' ? '**You**' : `**${selectedAgent?.name || 'Assistant'}**`
                    return `${role}\n\n${m.content}\n`
                  }).join('\n---\n\n')
                  const blob = new Blob([md], { type: 'text/markdown' })
                  const url = URL.createObjectURL(blob)
                  const a = document.createElement('a')
                  a.href = url
                  a.download = `chat-${new Date().toISOString().slice(0, 10)}.md`
                  a.click()
                  URL.revokeObjectURL(url)
                }}
                className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
                title="Export as Markdown"
                disabled={messages.length === 0}
              >
                <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
                  <path d="M8 2v8M5 7l3 3 3-3" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
                  <path d="M2 12v1a1 1 0 001 1h10a1 1 0 001-1v-1" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
                </svg>
              </button>
              {/* Fullscreen toggle */}
              <button
                onClick={() => {
                  if (document.fullscreenElement) document.exitFullscreen()
                  else document.documentElement.requestFullscreen().catch(() => {})
                }}
                className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors hidden sm:block"
                title="Fullscreen"
              >
                <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
                  <path d="M2 6V2h4M14 6V2h-4M2 10v4h4M14 10v4h-4" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </button>
              {/* Tool panel toggle */}
              <button
                onClick={() => setToolPanelOpen(!toolPanelOpen)}
                className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors relative"
                title="Tool activity"
              >
                <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
                  <rect x="1" y="2" width="14" height="12" rx="2" stroke="currentColor" strokeWidth="1.3" />
                  <line x1="10" y1="2" x2="10" y2="14" stroke="currentColor" strokeWidth="1.3" />
                </svg>
                {allToolCalls.length > 0 && (
                  <span className="absolute -top-0.5 -right-0.5 flex h-3.5 w-3.5 items-center justify-center rounded-full bg-primary text-[8px] font-bold text-primary-foreground">
                    {allToolCalls.length}
                  </span>
                )}
              </button>
            </div>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto">
            <div className="mx-auto max-w-2xl space-y-4 px-4 pt-5 pb-10 sm:px-6">
              {messages.length === 0 && !streamingText && !streaming && (
                <div className="flex flex-col items-center justify-center py-20 text-center sm:py-28">
                  {/* Agent avatar */}
                  <div className="mb-5 flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/10 ring-1 ring-primary/20">
                    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" className="text-primary">
                      <path d="M12 2a5 5 0 015 5v1h1a2 2 0 012 2v6a2 2 0 01-2 2H6a2 2 0 01-2-2V10a2 2 0 012-2h1V7a5 5 0 015-5z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/>
                      <circle cx="9" cy="13" r="1" fill="currentColor"/>
                      <circle cx="15" cy="13" r="1" fill="currentColor"/>
                    </svg>
                  </div>
                  <h3 className="text-lg font-semibold text-foreground tracking-tight">
                    {selectedAgent?.name || 'No agent selected'}
                  </h3>
                  {selectedAgent && (
                    <span className="mt-2 inline-flex items-center gap-1.5 rounded-full border border-border bg-muted/40 px-2.5 py-0.5 text-[11px] text-muted-foreground">
                      <span className="h-1.5 w-1.5 rounded-full bg-primary/60" />
                      {selectedAgent.model}
                    </span>
                  )}
                  <p className="mt-4 max-w-sm text-sm text-muted-foreground/80 leading-relaxed">
                    {selectedAgent?.system_prompt
                      ? selectedAgent.system_prompt.slice(0, 180) + (selectedAgent.system_prompt.length > 180 ? '…' : '')
                      : selectedAgent ? 'Send a message to start the conversation.' : 'Select an agent from the dropdown below to get started.'}
                  </p>
                  {selectedAgent && (
                    <div className="mt-6 grid grid-cols-1 gap-2 sm:grid-cols-2 max-w-md">
                      {[
                        { icon: '🐍', label: 'Write a Python script to analyze a CSV' },
                        { icon: '🎨', label: 'Generate an image of a cozy coffee shop' },
                        { icon: '📄', label: 'Create a professional resume in PDF' },
                        { icon: '📊', label: 'Make a chart comparing monthly sales' },
                      ].map((s) => (
                        <button
                          key={s.label}
                          onClick={() => setInput(s.label)}
                          className="group flex items-start gap-2.5 rounded-lg border border-border bg-card/50 p-3 text-left text-xs text-muted-foreground hover:border-primary/30 hover:bg-card hover:text-foreground transition-all"
                        >
                          <span className="text-base leading-none shrink-0 mt-0.5">{s.icon}</span>
                          <span className="leading-relaxed">{s.label}</span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {messages.map((msg) => {
                const text = getTextContent(msg)
                const isUser = msg.role === 'user'
                if (msg.role === 'tool') return null
                if (isUser) {
                  if (!text) return null
                  const attachmentMeta = msg.metadata?.attachments as Array<{filename: string; media_type: string; file_id: string}> | undefined
                  const quoteMeta = msg.metadata?.quote as { author: string; text: string } | undefined
                  const displayText = text
                  const isEditing = editingMsgId === msg.id

                  function submitEdit() {
                    const newText = editingText.trim()
                    if (!newText || !wsRef.current || streaming) return
                    const idx = messages.findIndex(m => m.id === msg.id)
                    // Remove this message and everything after it from local state
                    setMessages(prev => [
                      ...prev.slice(0, idx),
                      { ...prev[idx], content: newText },
                    ])
                    setEditingMsgId(null)
                    setStreaming(true)
                    streamingTextRef.current = ''
                    setStreamingText('')
                    setError('')
                    toolCallMapRef.current.clear()
                    toolCallOrderRef.current = []
                    setStreamToolCalls([])
                    // Server handles DB cleanup via resend flag
                    wsRef.current.send(JSON.stringify({
                      type: 'message',
                      resend: true,
                      content: newText,
                      conversation_id: conversationId,
                    }))
                  }

                  return (
                    <div key={msg.id} className="group flex flex-col items-end gap-1">
                      <div className="max-w-[82%] sm:max-w-[75%] w-full flex flex-col items-end">
                        {isEditing ? (
                          <div className="w-full rounded-2xl rounded-tr-sm bg-primary/10 border border-primary/30 overflow-hidden">
                            <textarea
                              autoFocus
                              value={editingText}
                              onChange={e => setEditingText(e.target.value)}
                              onKeyDown={e => {
                                if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submitEdit() }
                                if (e.key === 'Escape') setEditingMsgId(null)
                              }}
                              className="w-full resize-none bg-transparent px-4 pt-3 pb-2 text-[14.5px] leading-relaxed text-foreground focus:outline-none"
                              style={{ minHeight: '60px', maxHeight: '300px' }}
                            />
                            <div className="flex items-center justify-end gap-2 px-3 pb-2.5">
                              <button
                                onClick={() => setEditingMsgId(null)}
                                className="rounded-md px-2.5 py-1 text-xs text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                              >Cancel</button>
                              <button
                                onClick={submitEdit}
                                disabled={!editingText.trim() || streaming}
                                className="rounded-md bg-primary px-3 py-1 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-40 transition-colors"
                              >Send</button>
                            </div>
                          </div>
                        ) : (
                          <>
                            {quoteMeta && (
                              <div className="mb-1 max-w-full rounded-lg border-l-2 border-primary/60 bg-muted/40 px-2.5 py-1.5">
                                <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-muted-foreground/70 font-medium">
                                  <svg width="9" height="9" viewBox="0 0 14 14" fill="none">
                                    <path d="M2 11V8a3 3 0 013-3M2 11h2.5M2 11v.5a.5.5 0 00.5.5h2M8 11V8a3 3 0 013-3M8 11h2.5M8 11v.5a.5.5 0 00.5.5h2" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
                                  </svg>
                                  Replying to {quoteMeta.author}
                                </div>
                                <div className="mt-0.5 line-clamp-2 text-xs text-muted-foreground/90 break-words">
                                  {quoteMeta.text.length > 200 ? quoteMeta.text.slice(0, 200) + '…' : quoteMeta.text}
                                </div>
                              </div>
                            )}
                            <div className="rounded-2xl rounded-tr-sm bg-gradient-to-br from-primary to-primary/80 px-3.5 py-2 text-[14px] leading-relaxed text-primary-foreground shadow-sm">
                              <div className="whitespace-pre-wrap break-words">{displayText}</div>
                              {attachmentMeta && attachmentMeta.length > 0 && (
                              <div className="mt-2 flex flex-wrap gap-1.5">
                                {attachmentMeta.map(a => (
                                  <span key={a.file_id} className="inline-flex items-center gap-1 rounded-full bg-white/15 px-2 py-0.5 text-[11px]">
                                    <svg width="10" height="10" viewBox="0 0 14 14" fill="none"><path d="M3 2h5l3 3v7a1 1 0 01-1 1H3a1 1 0 01-1-1V3a1 1 0 011-1z" stroke="currentColor" strokeWidth="1.3"/></svg>
                                    {a.filename}
                                  </span>
                                ))}
                              </div>
                            )}
                          </div>
                          </>
                        )}
                      </div>
                      {/* Hover actions — hidden while editing */}
                      {!isEditing && (
                        <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity duration-150 pr-0.5">
                          <button
                            onClick={() => { setEditingText(text); setEditingMsgId(msg.id) }}
                            className="flex items-center gap-1 rounded-md px-2 py-1 text-[11px] text-muted-foreground/50 hover:text-muted-foreground hover:bg-muted transition-colors"
                          >
                            <svg width="11" height="11" viewBox="0 0 14 14" fill="none">
                              <path d="M9.5 2.5l2 2L4 12H2v-2L9.5 2.5z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round"/>
                            </svg>
                            Edit
                          </button>
                          <button
                            disabled={streaming}
                            onClick={() => {
                              if (!wsRef.current || streaming) return
                              // Trim local state to just up to and including this message
                              const idx = messages.findIndex(m => m.id === msg.id)
                              setMessages(prev => prev.slice(0, idx + 1))
                              setStreaming(true)
                              streamingTextRef.current = ''
                              setStreamingText('')
                              setError('')
                              toolCallMapRef.current.clear()
                              toolCallOrderRef.current = []
                              setStreamToolCalls([])
                              wsRef.current.send(JSON.stringify({
                                type: 'message',
                                resend: true,
                                content: text,
                                conversation_id: conversationId,
                              }))
                            }}
                            className="flex items-center gap-1 rounded-md px-2 py-1 text-[11px] text-muted-foreground/50 hover:text-muted-foreground hover:bg-muted transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                          >
                            <svg width="11" height="11" viewBox="0 0 14 14" fill="none">
                              <path d="M12 2L2 7l4 2 1 4 5-11z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round"/>
                            </svg>
                            Resend
                          </button>
                          <button
                            onClick={() => quoteMessage(text, 'You')}
                            className="flex items-center gap-1 rounded-md px-2 py-1 text-[11px] text-muted-foreground/50 hover:text-muted-foreground hover:bg-muted transition-colors"
                            title="Quote in reply"
                          >
                            <svg width="11" height="11" viewBox="0 0 14 14" fill="none">
                              <path d="M2 11V8a3 3 0 013-3M2 11h2.5M2 11v.5a.5.5 0 00.5.5h2M8 11V8a3 3 0 013-3M8 11h2.5M8 11v.5a.5.5 0 00.5.5h2" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
                            </svg>
                            Quote
                          </button>
                        </div>
                      )}
                    </div>
                  )
                }
                if (!text) return null
                const isLast = messages.findLastIndex(m => m.role === 'assistant') === messages.indexOf(msg)
                return (
                  <div key={msg.id} className="group flex justify-start gap-3">
                    {/* Agent avatar dot */}
                    <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/15 ring-1 ring-primary/20">
                      <svg width="12" height="12" viewBox="0 0 16 16" fill="none" className="text-primary">
                        <path d="M8 1a4 4 0 014 4v1h1a1 1 0 011 1v5a1 1 0 01-1 1H3a1 1 0 01-1-1V7a1 1 0 011-1h1V5a4 4 0 014-4z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round"/>
                        <circle cx="6" cy="9" r="0.75" fill="currentColor"/>
                        <circle cx="10" cy="9" r="0.75" fill="currentColor"/>
                      </svg>
                    </div>
                    <div className="min-w-0 flex-1 max-w-[85%]">
                      <div className="text-[14px] leading-[1.6] text-foreground agent-message">
                        <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>{text}</ReactMarkdown>
                      </div>
                      {/* Artifact chips */}
                      {(() => {
                        const arts = extractArtifacts(text, msg.id)
                        if (arts.length === 0) return null
                        return (
                          <div className="mt-2 flex flex-wrap gap-1.5">
                            {arts.map(a => (
                              <button
                                key={a.id}
                                onClick={() => openArtifact(a)}
                                className="inline-flex items-center gap-1.5 rounded-md border border-border bg-muted/40 px-2 py-1 text-[11px] text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
                                title="Open in panel"
                              >
                                <svg width="11" height="11" viewBox="0 0 16 16" fill="none">
                                  <rect x="2" y="1.5" width="9" height="13" rx="1.5" stroke="currentColor" strokeWidth="1.3"/>
                                  <path d="M11 4l3 3v7.5a.5.5 0 01-.5.5H5" stroke="currentColor" strokeWidth="1.3"/>
                                </svg>
                                <span className="truncate max-w-[200px]">{a.title}</span>
                                <span className="opacity-60">↗</span>
                              </button>
                            ))}
                          </div>
                        )
                      })()}
                      {/* Action toolbar — visible on hover */}
                      <div className="mt-2 flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity duration-150">
                        {/* Copy */}
                        <button
                          onClick={() => copyMessage(msg.id, text)}
                          className="flex items-center justify-center rounded-md p-1.5 text-muted-foreground/50 hover:text-muted-foreground hover:bg-muted transition-colors"
                          title="Copy"
                        >
                          {copiedMsgId === msg.id ? (
                            <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
                              <path d="M2 7l3.5 3.5 6.5-7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                            </svg>
                          ) : (
                            <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
                              <rect x="4" y="4" width="8" height="8" rx="1.5" stroke="currentColor" strokeWidth="1.3"/>
                              <path d="M10 4V3a1.5 1.5 0 00-1.5-1.5H3A1.5 1.5 0 001.5 3v5.5A1.5 1.5 0 003 10h1" stroke="currentColor" strokeWidth="1.3"/>
                            </svg>
                          )}
                        </button>
                        {/* Quote */}
                        <button
                          onClick={() => quoteMessage(text, selectedAgent?.name || 'Assistant')}
                          className="flex items-center justify-center rounded-md p-1.5 text-muted-foreground/50 hover:text-muted-foreground hover:bg-muted transition-colors"
                          title="Quote in reply"
                        >
                          <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
                            <path d="M2 11V8a3 3 0 013-3M2 11h2.5M2 11v.5a.5.5 0 00.5.5h2M8 11V8a3 3 0 013-3M8 11h2.5M8 11v.5a.5.5 0 00.5.5h2" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
                          </svg>
                        </button>
                        {/* Thumbs up */}
                        <button
                          onClick={() => thumbMessage(msg.id, 'up')}
                          className={`flex items-center justify-center rounded-md p-1.5 transition-colors ${
                            thumbedMsgId[msg.id] === 'up'
                              ? 'text-emerald-400'
                              : 'text-muted-foreground/50 hover:text-muted-foreground hover:bg-muted'
                          }`}
                          title="Good response"
                        >
                          <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
                            <path d="M4.5 6.5L6.5 1.5a1 1 0 011 1V5h3.5a1 1 0 011 1.1l-.7 5a1 1 0 01-1 .9H4.5V6.5z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" fill={thumbedMsgId[msg.id] === 'up' ? 'currentColor' : 'none'}/>
                            <path d="M4.5 6.5H2.5a.5.5 0 00-.5.5v5a.5.5 0 00.5.5h2V6.5z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" fill={thumbedMsgId[msg.id] === 'up' ? 'currentColor' : 'none'}/>
                          </svg>
                        </button>
                        {/* Thumbs down */}
                        <button
                          onClick={() => thumbMessage(msg.id, 'down')}
                          className={`flex items-center justify-center rounded-md p-1.5 transition-colors ${
                            thumbedMsgId[msg.id] === 'down'
                              ? 'text-destructive'
                              : 'text-muted-foreground/50 hover:text-muted-foreground hover:bg-muted'
                          }`}
                          title="Bad response"
                        >
                          <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
                            <path d="M9.5 7.5L7.5 12.5a1 1 0 01-1-1V9H3a1 1 0 01-1-1.1l.7-5A1 1 0 013.7 2H9.5v5.5z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" fill={thumbedMsgId[msg.id] === 'down' ? 'currentColor' : 'none'}/>
                            <path d="M9.5 7.5h2a.5.5 0 01.5-.5V2a.5.5 0 00-.5-.5h-2v6z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" fill={thumbedMsgId[msg.id] === 'down' ? 'currentColor' : 'none'}/>
                          </svg>
                        </button>
                        {/* Regenerate — only on last assistant message */}
                        {isLast && !streaming && (
                          <button
                            onClick={() => regenerateFrom(msg)}
                            className="flex items-center justify-center rounded-md p-1.5 text-muted-foreground/50 hover:text-muted-foreground hover:bg-muted transition-colors"
                            title="Regenerate"
                          >
                            <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
                              <path d="M2 7a5 5 0 015-5 5 5 0 014.5 2.8" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
                              <path d="M12 7a5 5 0 01-5 5 5 5 0 01-4.5-2.8" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
                              <path d="M10.5 1.5L12 4.8l-3.5.2" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
                              <path d="M3.5 12.5L2 9.2l3.5-.2" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
                            </svg>
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                )
              })}

              {/* Thinking indicator */}
              {streaming && !streamingText && streamToolCalls.length === 0 && (
                <div className="flex justify-start gap-3">
                  <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10 ring-1 ring-primary/20">
                    <span className="h-3 w-3 rounded-full border-2 border-primary border-t-transparent animate-spin" />
                  </div>
                  <div className="flex items-center gap-2 rounded-xl bg-muted/40 px-3.5 py-2 text-sm text-muted-foreground">
                    Thinking…
                  </div>
                </div>
              )}

              {/* Using tools indicator */}
              {streaming && !streamingText && streamToolCalls.length > 0 && (
                <div className="flex justify-start gap-3">
                  <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10 ring-1 ring-primary/20">
                    <span className="h-3 w-3 rounded-full border-2 border-primary border-t-transparent animate-spin" />
                  </div>
                  <div className="flex items-center gap-2 rounded-xl bg-muted/40 px-3.5 py-2 text-sm text-muted-foreground">
                    Using tools…
                  </div>
                </div>
              )}

              {/* Streaming text */}
              {streamingText && (
                <div className="flex justify-start gap-3">
                  <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/15 ring-1 ring-primary/20">
                    <svg width="12" height="12" viewBox="0 0 16 16" fill="none" className="text-primary">
                      <path d="M8 1a4 4 0 014 4v1h1a1 1 0 011 1v5a1 1 0 01-1 1H3a1 1 0 01-1-1V7a1 1 0 011-1h1V5a4 4 0 014-4z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round"/>
                    </svg>
                  </div>
                  <div className="min-w-0 flex-1 max-w-[85%] text-[14px] leading-[1.6] text-foreground agent-message">
                    <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>{streamingText}</ReactMarkdown>
                    <span className="inline-block h-4 w-0.5 blink-cursor bg-primary ml-0.5" />
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
          <div className="bg-background">
            <form onSubmit={(e) => { e.preventDefault(); sendMessage() }} className="mx-auto max-w-2xl px-3 pb-3 pt-1 sm:px-4 sm:pb-4">
              {tokenUsage.totalInput + tokenUsage.totalOutput > 0 && (
                <div className="flex justify-center pb-1">
                  <span className="text-[10px] text-muted-foreground/40">{(tokenUsage.totalInput + tokenUsage.totalOutput).toLocaleString()} tokens</span>
                </div>
              )}
              <div className="rounded-2xl border border-border bg-card/80 backdrop-blur-xl transition-colors focus-within:border-primary/50">
                {/* Quote preview */}
                {quotedRef && (
                  <div className="flex items-start gap-2 px-3 pt-2.5 pb-1">
                    <div className="flex-1 min-w-0 rounded-lg border-l-2 border-primary/60 bg-muted/40 px-2.5 py-1.5">
                      <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-muted-foreground/70 font-medium">
                        <svg width="9" height="9" viewBox="0 0 14 14" fill="none">
                          <path d="M2 11V8a3 3 0 013-3M2 11h2.5M2 11v.5a.5.5 0 00.5.5h2M8 11V8a3 3 0 013-3M8 11h2.5M8 11v.5a.5.5 0 00.5.5h2" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
                        </svg>
                        Replying to {quotedRef.author}
                      </div>
                      <div className="mt-0.5 line-clamp-2 text-xs text-muted-foreground/90 break-words">
                        {quotedRef.text.length > 200 ? quotedRef.text.slice(0, 200) + '…' : quotedRef.text}
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => setQuotedRef(null)}
                      className="shrink-0 rounded-md p-1 text-muted-foreground/50 hover:text-foreground hover:bg-muted transition-colors"
                      title="Remove quote"
                    >
                      <svg width="11" height="11" viewBox="0 0 14 14" fill="none"><path d="M3 3l8 8M11 3l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
                    </button>
                  </div>
                )}
                {/* Attachment previews */}
                {attachments.length > 0 && (
                  <div className="flex flex-wrap gap-2 px-3 pt-2.5 pb-1">
                    {attachments.map((att) => (
                      att.media_type.startsWith('image/') ? (
                        <div key={att.key} className="relative h-14 w-14 shrink-0 rounded-lg overflow-hidden border border-border bg-muted">
                          {att.uploading || !att.objectUrl ? (
                            <div className="h-full w-full animate-pulse bg-muted-foreground/10 flex items-center justify-center">
                              <svg width="14" height="14" viewBox="0 0 16 16" fill="none" className="text-muted-foreground animate-spin"><circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="2" strokeDasharray="12 24" /></svg>
                            </div>
                          ) : (
                            <img src={att.objectUrl} alt={att.filename} className="h-full w-full object-cover" />
                          )}
                          <button type="button" onClick={() => removeAttachment(att.key)} className="absolute -top-1 -right-1 flex h-4 w-4 items-center justify-center rounded-full bg-background border border-border text-muted-foreground hover:text-foreground">
                            <svg width="7" height="7" viewBox="0 0 10 10" fill="none"><path d="M2 2l6 6M8 2l-6 6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></svg>
                          </button>
                        </div>
                      ) : (
                        <div key={att.key} className="relative flex items-center gap-1.5 rounded-lg border border-border bg-background/30 px-2.5 py-1.5 text-xs text-foreground/70 max-w-[160px]">
                          <svg width="11" height="11" viewBox="0 0 16 16" fill="none" className="shrink-0 text-muted-foreground/60"><path d="M3 2h7l3 3v9a1 1 0 01-1 1H3a1 1 0 01-1-1V3a1 1 0 011-1z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round"/></svg>
                          {att.uploading && <svg width="10" height="10" viewBox="0 0 16 16" fill="none" className="shrink-0 text-muted-foreground animate-spin"><circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="2" strokeDasharray="12 24" /></svg>}
                          <span className="truncate">{att.filename}</span>
                          <button type="button" onClick={() => removeAttachment(att.key)} className="ml-0.5 shrink-0 text-muted-foreground/40 hover:text-foreground"><svg width="7" height="7" viewBox="0 0 10 10" fill="none"><path d="M2 2l6 6M8 2l-6 6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></svg></button>
                        </div>
                      )
                    ))}
                  </div>
                )}

                {/* Textarea row */}
                <div className="flex items-end gap-1 px-2 pt-2 pb-1.5">
                  <input ref={fileInputRef} type="file" multiple accept="image/*,video/*,audio/*,application/pdf,.txt,.md,.csv,.json,.docx,.xlsx" className="absolute w-0 h-0 overflow-hidden opacity-0" style={{ position: 'absolute', pointerEvents: 'none' }} tabIndex={-1} onChange={(e) => { const files = [...(e.target.files || [])]; files.forEach(handleFileSelect); e.target.value = '' }} />

                  <button type="button" onClick={() => fileInputRef.current?.click()} disabled={!connected || !selectedAgent} className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-muted-foreground/40 hover:text-muted-foreground transition-colors disabled:opacity-30" title="Attach">
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M8 3v10M3 8h10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></svg>
                  </button>

                  <textarea
                    ref={textareaRef}
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); if (!streaming) sendMessage() }
                      else if (e.key === 'Escape' && quotedRef && !input) { e.preventDefault(); setQuotedRef(null) }
                    }}
                    onPaste={(e) => { const items = [...e.clipboardData.items]; const img = items.find(i => i.type.startsWith('image/')); if (img) { e.preventDefault(); const file = img.getAsFile(); if (file) handleFileSelect(file) } }}
                    placeholder={!selectedAgent ? 'Select an agent…' : connected ? (streaming ? 'Generating…' : 'Message…') : 'Connecting…'}
                    disabled={!connected || !selectedAgent}
                    rows={1}
                    className="flex-1 resize-none border-0 bg-transparent px-1 py-1.5 text-sm text-foreground placeholder:text-muted-foreground/30 focus:outline-none"
                    style={{ maxHeight: '200px' }}
                  />

                  {streaming ? (
                    <button type="button" onClick={() => { wsRef.current?.send(JSON.stringify({ type: 'cancel' })); setStreaming(false); streamingTextRef.current = ''; setStreamingText('') }} className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-foreground/80 transition-colors hover:bg-foreground" title="Stop">
                      <svg width="10" height="10" viewBox="0 0 10 10" fill="none"><rect x="2" y="2" width="6" height="6" rx="0.5" fill="var(--color-background)" /></svg>
                    </button>
                  ) : (
                    <button type="submit" disabled={(!input.trim() && attachments.filter(a => !a.uploading).length === 0) || attachments.some(a => a.uploading) || !connected || !selectedAgent} className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground transition-all hover:bg-primary/90 disabled:opacity-20" title="Send">
                      <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M8 12V4M4 7.5L8 3.5 12 7.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /></svg>
                    </button>
                  )}
                </div>

                {/* Bottom bar: agent · model · tools */}
                <div className="relative flex items-center gap-1.5 px-2.5 pb-2 pt-0.5 overflow-x-auto" onMouseDown={e => e.stopPropagation()}>
                  {/* Agent selector */}
                  <div className="relative">
                    <button ref={agentBtnRef} type="button" onClick={() => { setAgentDropdownOpen(prev => !prev); setModelDropdownOpen(false); setToolsDropdownOpen(false) }} className="flex items-center gap-1.5 rounded-full border border-border px-2.5 py-1 text-[11px] text-foreground/70 hover:text-foreground hover:bg-secondary transition-colors">
                      <span className={`h-1.5 w-1.5 rounded-full shrink-0 ${connected ? 'bg-emerald-500' : 'bg-zinc-400'}`} />
                      <span className="max-w-[100px] truncate font-medium">{selectedAgent?.name ?? 'Agent'}</span>
                      <svg width="8" height="8" viewBox="0 0 10 10" fill="none" className="opacity-50"><path d="M2.5 6.5l2.5-2.5L7.5 6.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/></svg>
                    </button>
                    {agentDropdownOpen && createPortal(
                      <div className="min-w-[200px] max-w-[280px] rounded-xl border border-border bg-popover shadow-lg shadow-black/10 py-1" style={getDropdownStyle(agentBtnRef)} onMouseDown={e => e.stopPropagation()}>
                        {activeAgents.length === 0 && <div className="px-3 py-2 text-xs text-muted-foreground">No active agents</div>}
                        {activeAgents.map(agent => (
                          <button key={agent.id} type="button" onClick={() => selectAgent(agent.id, false)} className="flex w-full items-center gap-2 px-3 py-1.5 text-xs text-foreground/80 hover:bg-muted transition-colors text-left">
                            <span className={`h-1.5 w-1.5 rounded-full shrink-0 ${agent.id === selectedAgentId ? 'bg-primary' : 'bg-muted-foreground/30'}`} />
                            <span className="flex-1 truncate">{agent.name}</span>
                            {agent.id === selectedAgentId && <svg width="10" height="10" viewBox="0 0 12 12" fill="none" className="text-primary shrink-0"><path d="M2 6l3 3 5-5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>}
                          </button>
                        ))}
                        <div className="my-0.5 border-t border-border" />
                        {selectedAgentId && <Link to={`/agents/${selectedAgentId}/settings`} onClick={() => setAgentDropdownOpen(false)} className="flex w-full items-center gap-1.5 px-3 py-1.5 text-[11px] text-muted-foreground hover:text-foreground hover:bg-muted transition-colors">Settings</Link>}
                        <Link to="/dashboard" onClick={() => setAgentDropdownOpen(false)} className="flex w-full items-center gap-1.5 px-3 py-1.5 text-[11px] text-muted-foreground hover:text-foreground hover:bg-muted transition-colors">+ New agent</Link>
                      </div>,
                      document.body
                    )}
                  </div>

                  {/* Model selector */}
                  {selectedAgent && (
                    <div className="relative">
                      <button ref={modelBtnRef} type="button" onClick={() => { setModelDropdownOpen(prev => !prev); setAgentDropdownOpen(false); setToolsDropdownOpen(false) }} className="flex items-center gap-1.5 rounded-full border border-border px-2.5 py-1 text-[11px] text-foreground/70 hover:text-foreground hover:bg-secondary transition-colors">
                        <span className="max-w-[120px] truncate">{selectedAgent.model}</span>
                        <svg width="8" height="8" viewBox="0 0 10 10" fill="none" className="opacity-50"><path d="M2.5 6.5l2.5-2.5L7.5 6.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/></svg>
                      </button>
                      {modelDropdownOpen && createPortal(
                        <div className="w-56 max-h-64 overflow-y-auto rounded-xl border border-border bg-popover shadow-lg shadow-black/10 py-1" style={getDropdownStyle(modelBtnRef)} onMouseDown={e => e.stopPropagation()}>
                          {availableModels.length === 0 && <div className="px-3 py-2 text-xs text-muted-foreground">Loading…</div>}
                          {availableModels.map(m => (
                            <button key={m} type="button" onClick={() => { updateAgentLocal({ model: m }); setModelDropdownOpen(false) }} className="flex w-full items-center gap-2 px-3 py-1.5 text-xs text-foreground/80 hover:bg-muted transition-colors text-left">
                              <span className={`h-1.5 w-1.5 rounded-full shrink-0 ${m === selectedAgent.model ? 'bg-primary' : 'bg-muted-foreground/30'}`} />
                              <span className="flex-1 truncate">{m}</span>
                              {m === selectedAgent.model && <svg width="10" height="10" viewBox="0 0 12 12" fill="none" className="text-primary shrink-0"><path d="M2 6l3 3 5-5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>}
                            </button>
                          ))}
                        </div>,
                        document.body
                      )}
                    </div>
                  )}

                  {/* Tools toggle */}
                  {selectedAgent && (
                    <div className="relative">
                      <button ref={toolsBtnRef} type="button" onClick={() => { setToolsDropdownOpen(prev => !prev); setAgentDropdownOpen(false); setModelDropdownOpen(false) }} className="flex items-center gap-1.5 rounded-full border border-border px-2.5 py-1 text-[11px] text-foreground/70 hover:text-foreground hover:bg-secondary transition-colors">
                        <span>{selectedAgent.allowed_tools.length} tools</span>
                        <svg width="8" height="8" viewBox="0 0 10 10" fill="none" className="opacity-50"><path d="M2.5 6.5l2.5-2.5L7.5 6.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/></svg>
                      </button>
                      {toolsDropdownOpen && createPortal(
                        <div className="w-52 max-h-64 overflow-y-auto rounded-xl border border-border bg-popover shadow-lg shadow-black/10 py-1" style={getDropdownStyle(toolsBtnRef)} onMouseDown={e => e.stopPropagation()}>
                          <div className="flex items-center justify-between px-3 py-1.5">
                            <span className="text-[10px] text-muted-foreground uppercase tracking-wider font-medium">Tools</span>
                            <div className="flex gap-2">
                              <button type="button" onClick={() => updateAgentLocal({ allowed_tools: ALL_TOOLS.map(t => t.id) })} className="text-[10px] text-primary hover:underline">All</button>
                              <button type="button" onClick={() => updateAgentLocal({ allowed_tools: [] })} className="text-[10px] text-muted-foreground hover:underline">None</button>
                            </div>
                          </div>
                          {ALL_TOOLS.map(tool => {
                            const on = selectedAgent.allowed_tools.includes(tool.id)
                            return (
                              <button key={tool.id} type="button" onClick={() => { const u = on ? selectedAgent.allowed_tools.filter(t => t !== tool.id) : [...selectedAgent.allowed_tools, tool.id]; updateAgentLocal({ allowed_tools: u }) }} className="flex w-full items-center gap-2 px-3 py-1 text-xs hover:bg-muted transition-colors text-left">
                                <span className={`flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded border ${on ? 'bg-primary border-primary' : 'border-muted-foreground/30'}`}>
                                  {on && <svg width="8" height="8" viewBox="0 0 10 10" fill="none"><path d="M2 5l2.5 2.5L8 3" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>}
                                </span>
                                <span className={on ? 'text-foreground' : 'text-muted-foreground'}>{tool.name}</span>
                              </button>
                            )
                          })}
                        </div>,
                        document.body
                      )}
                    </div>
                  )}

                  <div className="flex-1" />
                  <button type="button" onClick={() => setToolPanelOpen(!toolPanelOpen)} className={`hidden md:flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] transition-colors ${toolPanelOpen ? 'text-primary' : 'text-muted-foreground/40 hover:text-muted-foreground'}`} title="Tool activity">
                    <svg width="10" height="10" viewBox="0 0 14 14" fill="none"><rect x="1" y="2" width="12" height="10" rx="1.5" stroke="currentColor" strokeWidth="1.2"/><line x1="9" y1="2" x2="9" y2="12" stroke="currentColor" strokeWidth="1.2"/></svg>
                    {allToolCalls.length > 0 && <span className="text-[9px] text-primary">{allToolCalls.length}</span>}
                  </button>
                </div>
              </div>
              {/* Keyboard hint */}
              <div className="mx-auto mt-1.5 max-w-2xl px-6 text-[10px] text-muted-foreground/50 text-center select-none">
                <kbd className="inline-block px-1 font-mono">⏎</kbd> to send
                <span className="mx-1.5 opacity-40">·</span>
                <kbd className="inline-block px-1 font-mono">Shift</kbd>+<kbd className="inline-block px-1 font-mono">⏎</kbd> for newline
                <span className="mx-1.5 opacity-40">·</span>
                <kbd className="inline-block px-1 font-mono">⌘K</kbd> command palette
              </div>
            </form>
          </div>
        </main>

        {/* Mobile tool panel overlay */}
        {toolPanelOpen && (
          <div className="fixed inset-0 z-30 bg-black/60 md:hidden" onClick={() => setToolPanelOpen(false)} />
        )}

        {/* Right Panel (Tools | Artifacts tabs) */}
        {toolPanelOpen && (
          <aside className="fixed inset-y-0 right-0 z-40 flex w-80 flex-col border-l border-border bg-sidebar transition-transform duration-200 md:relative md:z-auto md:w-72 md:translate-x-0">
            {/* Tabs */}
            <div className="flex items-center justify-between border-b border-border px-2 py-2">
              <div className="flex items-center gap-0.5">
                <button
                  onClick={() => setRightTab('tools')}
                  className={`flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs transition-colors ${rightTab === 'tools' ? 'bg-muted text-foreground' : 'text-muted-foreground hover:text-foreground'}`}
                >
                  <svg width="12" height="12" viewBox="0 0 16 16" fill="none">
                    <path d="M8 1v4M8 11v4M1 8h4M11 8h4M3.5 3.5l2.5 2.5M10 10l2.5 2.5M3.5 12.5L6 10M10 6l2.5-2.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                  </svg>
                  Tools
                  {allToolCalls.length > 0 && (
                    <span className="rounded-full bg-muted-foreground/15 px-1.5 text-[9px]">{allToolCalls.length}</span>
                  )}
                </button>
                <button
                  onClick={() => setRightTab('artifacts')}
                  className={`flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs transition-colors ${rightTab === 'artifacts' ? 'bg-muted text-foreground' : 'text-muted-foreground hover:text-foreground'}`}
                >
                  <svg width="12" height="12" viewBox="0 0 16 16" fill="none">
                    <rect x="2" y="1.5" width="9" height="13" rx="1.5" stroke="currentColor" strokeWidth="1.3"/>
                    <path d="M11 4l3 3v7.5a.5.5 0 01-.5.5H5" stroke="currentColor" strokeWidth="1.3"/>
                  </svg>
                  Artifact
                </button>
              </div>
              <button onClick={() => setToolPanelOpen(false)} className="rounded p-1 text-muted-foreground hover:text-foreground">
                <svg width="13" height="13" viewBox="0 0 14 14" fill="none"><path d="M3 3l8 8M11 3l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></svg>
              </button>
            </div>

            {rightTab === 'tools' ? (
              <div className="flex-1 overflow-y-auto p-3 space-y-1">
                {allToolCalls.length === 0 && (
                  <div className="flex flex-col items-center justify-center py-12 text-center">
                    <svg width="24" height="24" viewBox="0 0 16 16" fill="none" className="text-muted-foreground/30 mb-2">
                      <path d="M8 1v4M8 11v4M1 8h4M11 8h4M3.5 3.5l2.5 2.5M10 10l2.5 2.5M3.5 12.5L6 10M10 6l2.5-2.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                    </svg>
                    <p className="text-xs text-muted-foreground">No tool calls yet</p>
                  </div>
                )}
                {allToolCalls.map((tc) => (
                  <ToolCallBlock key={tc.id} tool={tc} />
                ))}
                <div ref={toolPanelBottomRef} />
              </div>
            ) : (
              <div className="flex-1 overflow-hidden">
                {activeArtifact ? (
                  <ArtifactsPanel artifact={activeArtifact} onClose={() => setActiveArtifact(null)} />
                ) : (
                  <div className="flex flex-col items-center justify-center h-full py-12 text-center px-4">
                    <svg width="28" height="28" viewBox="0 0 16 16" fill="none" className="text-muted-foreground/30 mb-2">
                      <rect x="2" y="1.5" width="9" height="13" rx="1.5" stroke="currentColor" strokeWidth="1.3"/>
                      <path d="M11 4l3 3v7.5a.5.5 0 01-.5.5H5" stroke="currentColor" strokeWidth="1.3"/>
                    </svg>
                    <p className="text-xs text-muted-foreground">No artifact open</p>
                    <p className="text-[10px] text-muted-foreground/60 mt-1">Large code blocks &amp; files appear here</p>
                  </div>
                )}
              </div>
            )}
          </aside>
        )}
      </div>
    </div>
  )
}
