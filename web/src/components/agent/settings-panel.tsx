import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { updateAgent } from '@/api/agents'
import { listModels } from '@/api/models'
import { listMCPServers, addMCPServer, removeMCPServer, probeMCPServer, updateMCPServer, updateMCPServerTools, type MCPServer, type MCPToolInfo } from '@/api/mcp'
import type { Agent } from '@/types'

const ALL_TOOLS = [
  { id: 'web_search', name: 'Web Search', desc: 'Search the web for current information, news, prices, etc.' },
  { id: 'web_fetch', name: 'Web Fetch', desc: 'Fetch and read specific web pages' },
  { id: 'bash', name: 'Bash Shell', desc: 'Execute shell commands' },
  { id: 'file_read', name: 'File Read', desc: 'Read files from sandbox' },
  { id: 'file_write', name: 'File Write', desc: 'Write files to sandbox' },
  { id: 'file_list', name: 'File List', desc: 'List directory contents' },
  { id: 'manage_schedules', name: 'Manage Schedules', desc: 'Create, list, and delete scheduled tasks via conversation' },
  { id: 'knowledge_base', name: 'Knowledge Base', desc: 'Search, add URLs/text, and manage the agent\'s knowledge base' },
  { id: 'delegate_to_agent', name: 'Delegate to Agent', desc: 'Delegate tasks to other agents for multi-agent collaboration' },
  // Video tools
  { id: 'video_probe', name: 'Video Probe', desc: 'Inspect video/audio files — codec, resolution, duration, streams' },
  { id: 'video_cut', name: 'Video Cut', desc: 'Cut a time segment from a video (lossless stream-copy or re-encode)' },
  { id: 'video_concat', name: 'Video Concat', desc: 'Join multiple video clips into a single file' },
  { id: 'video_add_audio', name: 'Video Add Audio', desc: 'Replace or mix an audio track into a video' },
  { id: 'video_thumbnail', name: 'Video Thumbnail', desc: 'Extract a JPEG frame from a video at any timestamp' },
  { id: 'video_export', name: 'Video Export', desc: 'Transcode video — change format, codec, resolution, bitrate, or export as GIF' },
  { id: 'video_overlay_text', name: 'Video Overlay Text', desc: 'Burn text / titles / captions onto a video' },
  { id: 'video_speed', name: 'Video Speed', desc: 'Change playback speed (time-lapse or slow motion)' },
  // Image generation
  { id: 'image_generate', name: 'Image Generate', desc: 'Generate images from text descriptions using DALL-E' },
  // File export
  { id: 'file_export', name: 'File Export', desc: 'Make sandbox files downloadable (PDF, DOCX, CSV, images, etc.)' },
  // Python interpreter
  { id: 'python', name: 'Python Interpreter', desc: 'Execute Python code with persistent state, pandas, matplotlib, numpy, etc.' },
]

interface Props { agent: Agent; onUpdate: (agent: Agent) => void }

export function AgentSettingsPanel({ agent, onUpdate }: Props) {
  const [name, setName] = useState(agent.name)
  const [systemPrompt, setSystemPrompt] = useState(agent.system_prompt)
  const [model, setModel] = useState(agent.model)
  const [temperature, setTemperature] = useState(agent.temperature)
  const [maxTokens, setMaxTokens] = useState(agent.max_tokens)
  const [tools, setTools] = useState<string[]>(agent.allowed_tools)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [availableModels, setAvailableModels] = useState<string[]>([])

  // MCP state
  const [mcpServers, setMcpServers] = useState<MCPServer[]>([])
  const [showAddMcp, setShowAddMcp] = useState(false)
  const [mcpTransport, setMcpTransport] = useState<'stdio' | 'http'>('stdio')
  const [mcpId, setMcpId] = useState('')
  const [mcpCommand, setMcpCommand] = useState('')
  const [mcpArgs, setMcpArgs] = useState('')
  const [mcpUrl, setMcpUrl] = useState('')
  const [mcpEnvPairs, setMcpEnvPairs] = useState<{ key: string; value: string }[]>([])
  const [addingMcp, setAddingMcp] = useState(false)

  // Tool discovery state (shared between add flow and existing server refresh)
  const [discoveringServerId, setDiscoveringServerId] = useState<string | null>(null)
  const [probing, setProbing] = useState(false)
  const [probeResults, setProbeResults] = useState<MCPToolInfo[] | null>(null)
  const [selectedMcpTools, setSelectedMcpTools] = useState<string[]>([])
  const [probeError, setProbeError] = useState<string | null>(null)

  // Inline edit state for existing servers
  const [editingServerId, setEditingServerId] = useState<string | null>(null)
  const [editCommand, setEditCommand] = useState('')
  const [editArgs, setEditArgs] = useState('')
  const [editUrl, setEditUrl] = useState('')
  const [editEnvPairs, setEditEnvPairs] = useState<{ key: string; value: string }[]>([])
  const [savingServer, setSavingServer] = useState(false)

  useEffect(() => {
    setName(agent.name); setSystemPrompt(agent.system_prompt); setModel(agent.model)
    setTemperature(agent.temperature); setMaxTokens(agent.max_tokens)
    setTools(agent.allowed_tools)
  }, [agent])

  useEffect(() => {
    listModels().then(({ models }) => setAvailableModels(models)).catch(() => {})
  }, [])

  useEffect(() => {
    listMCPServers(agent.id).then(({ mcp_servers }) => setMcpServers(mcp_servers)).catch(() => {})
  }, [agent.id])

  async function handleSave() {
    setSaving(true); setSaved(false)
    try {
      const { agent: updated } = await updateAgent(agent.id, {
        name, system_prompt: systemPrompt, model, temperature, max_tokens: maxTokens, allowed_tools: tools,
      })
      onUpdate(updated); setSaved(true); setTimeout(() => setSaved(false), 2000)
    } catch {} finally { setSaving(false) }
  }

  function toggleTool(id: string) { setTools(p => p.includes(id) ? p.filter(t => t !== id) : [...p, id]) }

  // ── Probe tools for a server ──
  async function probeServer(server: MCPServer): Promise<MCPToolInfo[] | null> {
    setProbing(true); setProbeError(null); setProbeResults(null)
    try {
      const { tools: discovered } = await probeMCPServer(agent.id, {
        command: server.command, args: server.args, env: server.env,
        url: server.url, headers: server.headers, transport: server.transport,
        oauth_token: server.oauth_token,
      })
      setProbeResults(discovered)
      setSelectedMcpTools(discovered.map(t => t.name)) // Select all by default
      return discovered
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Failed to discover tools'
      setProbeError(msg)
      return null
    } finally { setProbing(false) }
  }

  // ── Save selected tools to server metadata ──
  async function saveSelectedTools(serverId: string) {
    try {
      const { mcp_servers } = await updateMCPServerTools(agent.id, serverId, selectedMcpTools)
      setMcpServers(mcp_servers)
      setDiscoveringServerId(null)
      setProbeResults(null); setProbeError(null)
    } catch {}
  }

  // ── OAuth flow for HTTP servers ──
  function startOAuth(serverId: string): Promise<boolean> {
    return new Promise(async (resolve) => {
      try {
        const resp = await fetch(`/api/agents/${agent.id}/mcp-servers/${serverId}/auth`, {
          headers: { 'Authorization': `Bearer ${localStorage.getItem('aegis_access_token')}` },
        })
        if (!resp.ok) {
          // No OAuth required — that's fine, proceed without it
          resolve(true); return
        }
        const data = await resp.json()
        if (!data.auth_url) { resolve(true); return }

        const handleMessage = async (event: MessageEvent) => {
          if (event.data?.type === 'mcp-oauth-code' && event.data.code) {
            window.removeEventListener('message', handleMessage)
            try {
              const exchangeResp = await fetch('/api/mcp-oauth/exchange', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${localStorage.getItem('aegis_access_token')}` },
                body: JSON.stringify({ agent_id: agent.id, server_id: serverId, code: event.data.code, code_verifier: data.code_verifier }),
              })
              if (exchangeResp.ok) {
                // Reload servers to get the updated oauth_token
                const { mcp_servers } = await listMCPServers(agent.id)
                setMcpServers(mcp_servers)
                resolve(true)
              } else {
                resolve(false)
              }
            } catch { resolve(false) }
          } else if (event.data?.type === 'mcp-oauth-error') {
            window.removeEventListener('message', handleMessage)
            resolve(false)
          }
        }
        window.addEventListener('message', handleMessage)
        window.open(data.auth_url, 'mcp-oauth', 'width=600,height=700')
      } catch { resolve(true) } // If OAuth check itself fails, still proceed
    })
  }

  // ── Add MCP Server: save → auth (if HTTP) → auto-discover tools ──
  async function handleAddMcp() {
    setAddingMcp(true); setProbeError(null)
    try {
      const env: Record<string, string> = {}
      mcpEnvPairs.forEach(p => { if (p.key.trim()) env[p.key.trim()] = p.value })
      const server: MCPServer = {
        id: mcpId.trim(), transport: mcpTransport, enabled: true,
        env: Object.keys(env).length > 0 ? env : undefined,
      }
      if (mcpTransport === 'stdio') {
        server.command = mcpCommand.trim()
        server.args = mcpArgs.trim() ? mcpArgs.trim().split(/\s+/) : []
      } else {
        server.url = mcpUrl.trim()
      }

      // Step 1: Save the server first
      const { mcp_servers } = await addMCPServer(agent.id, server)
      setMcpServers(mcp_servers)
      setShowAddMcp(false)
      setMcpId(''); setMcpCommand(''); setMcpArgs(''); setMcpUrl(''); setMcpEnvPairs([])

      const savedServer = mcp_servers.find(s => s.id === server.id)
      if (!savedServer) return

      // Step 2: For HTTP, do OAuth first
      if (mcpTransport === 'http') {
        setDiscoveringServerId(savedServer.id)
        setProbing(true)
        const authOk = await startOAuth(savedServer.id)
        if (!authOk) {
          setProbeError('Authorization failed. Click "Authorize" to try again, then "Refresh Tools".')
          setProbing(false)
          return
        }
        // Reload to get token
        const { mcp_servers: refreshed } = await listMCPServers(agent.id)
        setMcpServers(refreshed)
        const authedServer = refreshed.find(s => s.id === savedServer.id)
        if (authedServer) {
          setDiscoveringServerId(authedServer.id)
          await probeServer(authedServer)
        }
      } else {
        // Step 2 (stdio): Auto-discover tools immediately
        setDiscoveringServerId(savedServer.id)
        await probeServer(savedServer)
      }
    } catch (e) {
      setProbeError(e instanceof Error ? e.message : 'Failed to add server')
    } finally { setAddingMcp(false) }
  }

  async function handleRemoveMcp(serverId: string) {
    if (!confirm(`Remove "${serverId}"?`)) return
    try {
      await removeMCPServer(agent.id, serverId)
      setMcpServers(p => p.filter(s => s.id !== serverId))
      if (discoveringServerId === serverId) {
        setDiscoveringServerId(null); setProbeResults(null); setProbeError(null)
      }
    } catch {}
  }

  // ── Refresh tools on an existing server ──
  async function handleRefreshTools(server: MCPServer) {
    setDiscoveringServerId(server.id)
    const discovered = await probeServer(server)
    if (discovered && server.enabled_tools?.length) {
      // Pre-select previously selected tools that still exist
      const validPrevious = server.enabled_tools.filter(t => discovered.some(d => d.name === t))
      setSelectedMcpTools(validPrevious.length > 0 ? validPrevious : discovered.map(t => t.name))
    }
  }

  // ── Re-auth an HTTP server, then auto-discover ──
  async function handleReAuth(server: MCPServer) {
    setDiscoveringServerId(server.id)
    setProbing(true); setProbeError(null); setProbeResults(null)
    const authOk = await startOAuth(server.id)
    if (!authOk) {
      setProbeError('Authorization failed.')
      setProbing(false)
      return
    }
    // Reload to get fresh token
    const { mcp_servers: refreshed } = await listMCPServers(agent.id)
    setMcpServers(refreshed)
    const authedServer = refreshed.find(s => s.id === server.id)
    if (authedServer) {
      await probeServer(authedServer)
    }
  }

  // ── Start editing an existing server ──
  function startEditServer(server: MCPServer) {
    setEditingServerId(server.id)
    setEditCommand(server.command || '')
    setEditArgs((server.args || []).join(' '))
    setEditUrl(server.url || '')
    const pairs = Object.entries(server.env || {}).map(([key, value]) => ({ key, value }))
    setEditEnvPairs(pairs)
    // Clear any open discovery panel for this server
    if (discoveringServerId === server.id) {
      setDiscoveringServerId(null); setProbeResults(null); setProbeError(null)
    }
  }

  function cancelEditServer() {
    setEditingServerId(null)
    setEditCommand(''); setEditArgs(''); setEditUrl(''); setEditEnvPairs([])
  }

  async function handleSaveServer(server: MCPServer) {
    setSavingServer(true)
    try {
      const env: Record<string, string> = {}
      editEnvPairs.forEach(p => { if (p.key.trim()) env[p.key.trim()] = p.value })

      const payload: Parameters<typeof updateMCPServer>[2] = {}
      if (server.transport !== 'http') {
        payload.command = editCommand.trim()
        payload.args = editArgs.trim() ? editArgs.trim().split(/\s+/) : []
      } else {
        payload.url = editUrl.trim()
      }
      payload.env = Object.keys(env).length > 0 ? env : {}

      const { mcp_servers } = await updateMCPServer(agent.id, server.id, payload)
      setMcpServers(mcp_servers)
      setEditingServerId(null)
      setEditCommand(''); setEditArgs(''); setEditUrl(''); setEditEnvPairs([])
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Failed to update server')
    } finally { setSavingServer(false) }
  }

  // ── Tool selection UI (reusable) ──
  function renderToolSelection(serverId: string) {
    if (discoveringServerId !== serverId) return null

    return (
      <div className="mt-3 space-y-2 border-t border-border pt-3">
        {probing && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground py-2">
            <span className="h-3 w-3 rounded-full border-2 border-primary border-t-transparent animate-spin" />
            Discovering tools...
          </div>
        )}

        {probeError && (
          <div className="rounded-md bg-destructive/10 px-3 py-2 text-xs text-destructive">{probeError}</div>
        )}

        {probeResults && probeResults.length === 0 && (
          <div className="text-xs text-muted-foreground py-1">No tools found on this server.</div>
        )}

        {probeResults && probeResults.length > 0 && (
          <>
            <div className="flex items-center justify-between">
              <Label className="text-xs">Found {probeResults.length} tools — select which to enable:</Label>
              <div className="flex gap-2">
                <button onClick={() => setSelectedMcpTools(probeResults.map(t => t.name))} className="text-[10px] text-primary hover:underline">All</button>
                <button onClick={() => setSelectedMcpTools([])} className="text-[10px] text-muted-foreground hover:underline">None</button>
              </div>
            </div>
            <div className="max-h-48 overflow-y-auto space-y-1">
              {probeResults.map((tool) => (
                <label key={tool.name} className="flex items-start gap-2 rounded border border-border p-2 cursor-pointer hover:bg-muted/50 text-xs">
                  <input type="checkbox" className="mt-0.5 h-3.5 w-3.5 accent-primary"
                    checked={selectedMcpTools.includes(tool.name)}
                    onChange={() => setSelectedMcpTools(prev => prev.includes(tool.name) ? prev.filter(t => t !== tool.name) : [...prev, tool.name])} />
                  <div className="min-w-0">
                    <div className="font-mono font-medium text-foreground">{tool.name}</div>
                    {tool.description && <div className="text-muted-foreground mt-0.5 line-clamp-2">{tool.description}</div>}
                  </div>
                </label>
              ))}
            </div>
            <div className="flex items-center gap-2">
              <Button size="sm" onClick={() => saveSelectedTools(serverId)} disabled={selectedMcpTools.length === 0}>
                Save ({selectedMcpTools.length} tools)
              </Button>
              <button onClick={() => { setDiscoveringServerId(null); setProbeResults(null); setProbeError(null) }}
                className="text-xs text-muted-foreground hover:text-foreground">Cancel</button>
            </div>
          </>
        )}
      </div>
    )
  }

  const canAdd = mcpId.trim() && (mcpTransport === 'stdio' ? mcpCommand.trim() : mcpUrl.trim())

  return (
    <div className="mx-auto max-w-2xl space-y-8 p-6">
      <h2 className="text-lg font-semibold text-foreground">Agent Settings</h2>

      <div className="space-y-2">
        <Label>Name</Label>
        <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="My Agent" />
      </div>

      <div className="space-y-2">
        <Label>System Prompt</Label>
        <textarea value={systemPrompt} onChange={(e) => setSystemPrompt(e.target.value)} rows={6}
          className="flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
          placeholder="You are a helpful assistant that..." />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label>Model</Label>
          <select value={model} onChange={(e) => setModel(e.target.value)}
            className="flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring">
            {availableModels.length > 0 ? (
              <>
                {availableModels.map(m => (
                  <option key={m} value={m}>{m}</option>
                ))}
                {/* Show current model if not in the list (e.g. legacy saved model) */}
                {!availableModels.includes(model) && (
                  <option value={model}>{model}</option>
                )}
              </>
            ) : (
              /* Fallback while loading or if no proxy */
              <>
                <option value="claude-sonnet-4-5">claude-sonnet-4-5</option>
                <option value="claude-opus-4-5">claude-opus-4-5</option>
                <option value="claude-haiku-4-5">claude-haiku-4-5</option>
                <option value="gpt-4.1">gpt-4.1</option>
                {model && !['claude-sonnet-4-5','claude-opus-4-5','claude-haiku-4-5','gpt-4.1'].includes(model) && (
                  <option value={model}>{model}</option>
                )}
              </>
            )}
          </select>
        </div>
        <div className="space-y-2">
          <Label>Temperature ({temperature})</Label>
          <input type="range" min="0" max="1" step="0.1" value={temperature}
            onChange={(e) => setTemperature(parseFloat(e.target.value))} className="w-full accent-primary" />
        </div>
      </div>

      <div className="space-y-2">
        <Label>Max Tokens</Label>
        <Input type="number" value={maxTokens} onChange={(e) => setMaxTokens(parseInt(e.target.value) || 4096)} />
      </div>

      {/* Built-in Tools */}
      <div className="space-y-3">
        <Label>Built-in Tools</Label>
        <div className="space-y-2">
          {ALL_TOOLS.map((tool) => (
            <label key={tool.id} className="flex items-center gap-3 rounded-lg border border-border p-3 cursor-pointer hover:bg-muted/50 transition-colors">
              <input type="checkbox" checked={tools.includes(tool.id)} onChange={() => toggleTool(tool.id)} className="h-4 w-4 rounded accent-primary" />
              <div>
                <div className="text-sm font-medium text-foreground">{tool.name}</div>
                <div className="text-xs text-muted-foreground">{tool.desc}</div>
              </div>
            </label>
          ))}
        </div>
      </div>

      {/* MCP Servers */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <Label>MCP Tool Servers</Label>
            <p className="text-xs text-muted-foreground mt-0.5">Connect external tools via MCP</p>
          </div>
          <button onClick={() => { setShowAddMcp(!showAddMcp); setProbeResults(null); setProbeError(null); setDiscoveringServerId(null) }}
            className="text-xs text-primary hover:underline">{showAddMcp ? 'Cancel' : '+ Add Server'}</button>
        </div>

        {/* Add new server form */}
        {showAddMcp && (
          <div className="space-y-3 rounded-lg border border-primary/30 p-4">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label className="text-xs">Server ID</Label>
                <Input value={mcpId} onChange={(e) => setMcpId(e.target.value)} placeholder="github" className="font-mono text-xs" />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Transport</Label>
                <div className="flex gap-1">
                  <button onClick={() => setMcpTransport('stdio')} className={`flex-1 rounded px-2 py-1.5 text-xs ${mcpTransport === 'stdio' ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground'}`}>stdio</button>
                  <button onClick={() => setMcpTransport('http')} className={`flex-1 rounded px-2 py-1.5 text-xs ${mcpTransport === 'http' ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground'}`}>HTTP</button>
                </div>
              </div>
            </div>
            {mcpTransport === 'stdio' ? (
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1"><Label className="text-xs">Command</Label><Input value={mcpCommand} onChange={(e) => setMcpCommand(e.target.value)} placeholder="npx" className="font-mono text-xs" /></div>
                <div className="space-y-1"><Label className="text-xs">Arguments</Label><Input value={mcpArgs} onChange={(e) => setMcpArgs(e.target.value)} placeholder="-y @mcp/server-github" className="font-mono text-xs" /></div>
              </div>
            ) : (
              <div className="space-y-1"><Label className="text-xs">Server URL</Label><Input value={mcpUrl} onChange={(e) => setMcpUrl(e.target.value)} placeholder="http://localhost:3001/mcp" className="font-mono text-xs" /></div>
            )}
            {mcpEnvPairs.map((pair, i) => (
              <div key={i} className="flex gap-2">
                <Input value={pair.key} onChange={(e) => setMcpEnvPairs(p => p.map((x, j) => j === i ? {...x, key: e.target.value} : x))} placeholder="ENV_VAR" className="font-mono text-xs flex-1" />
                <Input value={pair.value} onChange={(e) => setMcpEnvPairs(p => p.map((x, j) => j === i ? {...x, value: e.target.value} : x))} placeholder="value" type="password" className="font-mono text-xs flex-1" />
                <button onClick={() => setMcpEnvPairs(p => p.filter((_, j) => j !== i))} className="text-muted-foreground hover:text-destructive text-xs">&#10005;</button>
              </div>
            ))}
            <div className="flex items-center gap-2">
              <Button size="sm" onClick={handleAddMcp} disabled={addingMcp || !canAdd}>
                {addingMcp ? (mcpTransport === 'http' ? 'Saving & Authorizing...' : 'Saving & Discovering...') : 'Add Server'}
              </Button>
              <button onClick={() => setMcpEnvPairs(p => [...p, { key: '', value: '' }])} className="text-xs text-muted-foreground hover:text-foreground">+ env var</button>
            </div>
            {mcpTransport === 'http' && (
              <p className="text-[10px] text-muted-foreground">After saving, you'll be prompted to authorize if the server requires OAuth.</p>
            )}
          </div>
        )}

        {/* Existing servers */}
        {mcpServers.map((server) => (
          <div key={server.id} className="rounded-lg border border-border p-3">
            {editingServerId === server.id ? (
              /* ── Inline edit mode ── */
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-foreground">Edit: {server.id}</span>
                  <button onClick={cancelEditServer} className="text-xs text-muted-foreground hover:text-foreground">Cancel</button>
                </div>
                {server.transport !== 'http' ? (
                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-1">
                      <Label className="text-xs">Command</Label>
                      <Input value={editCommand} onChange={e => setEditCommand(e.target.value)} placeholder="npx" className="font-mono text-xs" />
                    </div>
                    <div className="space-y-1">
                      <Label className="text-xs">Arguments</Label>
                      <Input value={editArgs} onChange={e => setEditArgs(e.target.value)} placeholder="-y @mcp/server --authentication azcli" className="font-mono text-xs" />
                    </div>
                  </div>
                ) : (
                  <div className="space-y-1">
                    <Label className="text-xs">Server URL</Label>
                    <Input value={editUrl} onChange={e => setEditUrl(e.target.value)} placeholder="http://localhost:3001/mcp" className="font-mono text-xs" />
                  </div>
                )}
                {/* Env vars */}
                <div className="space-y-2">
                  {editEnvPairs.map((pair, i) => (
                    <div key={i} className="flex gap-2">
                      <Input value={pair.key} onChange={e => setEditEnvPairs(p => p.map((x, j) => j === i ? {...x, key: e.target.value} : x))} placeholder="ENV_VAR" className="font-mono text-xs flex-1" />
                      <Input value={pair.value} onChange={e => setEditEnvPairs(p => p.map((x, j) => j === i ? {...x, value: e.target.value} : x))} placeholder="value" type="password" className="font-mono text-xs flex-1" />
                      <button onClick={() => setEditEnvPairs(p => p.filter((_, j) => j !== i))} className="text-muted-foreground hover:text-destructive text-xs">&#10005;</button>
                    </div>
                  ))}
                  <button onClick={() => setEditEnvPairs(p => [...p, { key: '', value: '' }])} className="text-xs text-muted-foreground hover:text-foreground">+ env var</button>
                </div>
                <div className="flex items-center gap-2">
                  <Button size="sm" onClick={() => handleSaveServer(server)} disabled={savingServer}>
                    {savingServer ? 'Saving...' : 'Save Changes'}
                  </Button>
                  <button onClick={cancelEditServer} className="text-xs text-muted-foreground hover:text-foreground">Cancel</button>
                </div>
              </div>
            ) : (
              /* ── View mode ── */
              <div>
                <div className="flex items-center justify-between">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-medium text-foreground">{server.id}</span>
                      <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium uppercase ${server.url ? 'bg-blue-500/20 text-blue-400' : 'bg-emerald-500/20 text-emerald-400'}`}>
                        {server.url ? 'HTTP' : 'stdio'}
                      </span>
                      {server.url && (
                        <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${server.oauth_token ? 'bg-emerald-500/20 text-emerald-400' : 'bg-yellow-500/20 text-yellow-400'}`}>
                          {server.oauth_token ? '\u2713 Authenticated' : 'Not Authenticated'}
                        </span>
                      )}
                    </div>
                    <div className="mt-0.5 font-mono text-[11px] text-muted-foreground truncate">
                      {server.command ? `${server.command} ${(server.args || []).join(' ')}` : server.url || ''}
                    </div>
                    {server.enabled_tools && server.enabled_tools.length > 0 && (
                      <div className="mt-1 text-[10px] text-muted-foreground">
                        {server.enabled_tools.length} tools: {server.enabled_tools.slice(0, 4).join(', ')}
                        {server.enabled_tools.length > 4 && ` +${server.enabled_tools.length - 4} more`}
                      </div>
                    )}
                    {(!server.enabled_tools || server.enabled_tools.length === 0) && (
                      <div className="mt-1 text-[10px] text-yellow-400">No tools selected — click "Refresh Tools" to discover</div>
                    )}
                  </div>
                  <div className="flex items-center gap-1 ml-2 shrink-0">
                    {server.url && !server.oauth_token && (
                      <button onClick={() => handleReAuth(server)}
                        className="rounded px-2 py-1 text-[10px] text-primary hover:bg-primary/10 font-medium"
                        disabled={probing && discoveringServerId === server.id}>
                        Authorize
                      </button>
                    )}
                    {server.url && server.oauth_token && (
                      <button onClick={() => handleReAuth(server)}
                        className="rounded px-2 py-1 text-[10px] text-muted-foreground hover:text-primary"
                        disabled={probing && discoveringServerId === server.id}>
                        Re-auth
                      </button>
                    )}
                    <button onClick={() => handleRefreshTools(server)}
                      className="rounded px-2 py-1 text-[10px] text-primary hover:bg-primary/10"
                      disabled={probing && discoveringServerId === server.id}>
                      {probing && discoveringServerId === server.id ? 'Discovering...' : 'Refresh Tools'}
                    </button>
                    <button onClick={() => startEditServer(server)}
                      className="rounded px-2 py-1 text-[10px] text-muted-foreground hover:text-foreground hover:bg-muted">
                      Edit
                    </button>
                    <button onClick={() => handleRemoveMcp(server.id)} className="rounded p-1 text-muted-foreground hover:bg-destructive/20 hover:text-destructive">
                      <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M3 3l8 8M11 3l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></svg>
                    </button>
                  </div>
                </div>

                {/* Tool selection (appears after discovery) */}
                {renderToolSelection(server.id)}
              </div>
            )}
          </div>
        ))}

        {mcpServers.length === 0 && !showAddMcp && (
          <div className="text-xs text-muted-foreground py-2">No MCP servers configured. Add one to connect external tools.</div>
        )}
      </div>

      <div className="flex items-center gap-3">
        <Button onClick={handleSave} disabled={saving}>{saving ? 'Saving...' : 'Save Settings'}</Button>
        {saved && <span className="text-sm text-emerald-500">Saved!</span>}
      </div>
    </div>
  )
}
