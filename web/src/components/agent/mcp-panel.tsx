import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { listMCPServers, addMCPServer, removeMCPServer, type MCPServer } from '@/api/mcp'

interface Props {
  agentId: string
}

export function MCPPanel({ agentId }: Props) {
  const [servers, setServers] = useState<MCPServer[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [transport, setTransport] = useState<'stdio' | 'http'>('stdio')
  const [id, setId] = useState('')
  // stdio fields
  const [command, setCommand] = useState('')
  const [args, setArgs] = useState('')
  // http fields
  const [url, setUrl] = useState('')
  // shared
  const [envPairs, setEnvPairs] = useState<{ key: string; value: string }[]>([])
  const [creating, setCreating] = useState(false)

  useEffect(() => { loadServers() }, [agentId])

  async function loadServers() {
    try {
      const { mcp_servers } = await listMCPServers(agentId)
      setServers(mcp_servers)
    } catch { /* ignore */ } finally { setLoading(false) }
  }

  async function handleCreate() {
    if (!id.trim()) return
    if (transport === 'stdio' && !command.trim()) return
    if (transport === 'http' && !url.trim()) return
    setCreating(true)
    try {
      const env: Record<string, string> = {}
      envPairs.forEach((p) => { if (p.key.trim()) env[p.key.trim()] = p.value })

      const server: MCPServer = {
        id: id.trim(),
        transport,
        enabled: true,
        env: Object.keys(env).length > 0 ? env : undefined,
      }

      if (transport === 'stdio') {
        server.command = command.trim()
        server.args = args.trim() ? args.trim().split(/\s+/) : []
      } else {
        server.url = url.trim()
      }

      const { mcp_servers } = await addMCPServer(agentId, server)
      setServers(mcp_servers)
      resetForm()
    } catch { /* ignore */ } finally { setCreating(false) }
  }

  function resetForm() {
    setId(''); setCommand(''); setArgs(''); setUrl('')
    setEnvPairs([]); setShowCreate(false)
  }

  async function handleDelete(serverId: string) {
    if (!confirm(`Remove MCP server "${serverId}"?`)) return
    try {
      await removeMCPServer(agentId, serverId)
      setServers((prev) => prev.filter((s) => s.id !== serverId))
    } catch { /* ignore */ }
  }

  function addEnvPair() { setEnvPairs((prev) => [...prev, { key: '', value: '' }]) }
  function updateEnvPair(i: number, f: 'key' | 'value', v: string) {
    setEnvPairs((prev) => prev.map((p, idx) => idx === i ? { ...p, [f]: v } : p))
  }
  function removeEnvPair(i: number) { setEnvPairs((prev) => prev.filter((_, idx) => idx !== i)) }

  function getTransportLabel(s: MCPServer): string {
    if (s.url) return 'HTTP'
    if (s.command) return 'stdio'
    return s.transport || 'stdio'
  }

  if (loading) return <div className="p-6 text-muted-foreground">Loading...</div>

  return (
    <div className="mx-auto max-w-2xl space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-foreground">MCP Servers</h2>
          <p className="text-xs text-muted-foreground mt-1">
            Connect external tool servers. Supports stdio (local process) and HTTP (remote URL).
          </p>
        </div>
        <Button size="sm" onClick={() => setShowCreate(!showCreate)}>
          {showCreate ? 'Cancel' : '+ Add Server'}
        </Button>
      </div>

      {showCreate && (
        <div className="space-y-4 rounded-lg border border-border p-4">
          <div className="space-y-2">
            <Label>Server ID</Label>
            <Input value={id} onChange={(e) => setId(e.target.value)} placeholder="github" className="font-mono" />
          </div>

          <div className="space-y-2">
            <Label>Transport</Label>
            <div className="flex gap-2">
              <button onClick={() => setTransport('stdio')}
                className={`rounded-md px-3 py-1.5 text-sm ${transport === 'stdio' ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground'}`}>
                stdio (local process)
              </button>
              <button onClick={() => setTransport('http')}
                className={`rounded-md px-3 py-1.5 text-sm ${transport === 'http' ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground'}`}>
                HTTP (remote URL)
              </button>
            </div>
          </div>

          {transport === 'stdio' ? (
            <>
              <div className="space-y-2">
                <Label>Command</Label>
                <Input value={command} onChange={(e) => setCommand(e.target.value)} placeholder="npx" className="font-mono" />
              </div>
              <div className="space-y-2">
                <Label>Arguments (space-separated)</Label>
                <Input value={args} onChange={(e) => setArgs(e.target.value)}
                  placeholder="-y @modelcontextprotocol/server-github" className="font-mono" />
              </div>
            </>
          ) : (
            <div className="space-y-2">
              <Label>Server URL</Label>
              <Input value={url} onChange={(e) => setUrl(e.target.value)}
                placeholder="http://localhost:3001/mcp" className="font-mono" />
            </div>
          )}

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label>Environment Variables / Headers</Label>
              <button onClick={addEnvPair} className="text-xs text-primary hover:underline">+ Add</button>
            </div>
            {envPairs.map((pair, i) => (
              <div key={i} className="flex gap-2">
                <Input value={pair.key} onChange={(e) => updateEnvPair(i, 'key', e.target.value)}
                  placeholder="GITHUB_TOKEN" className="font-mono flex-1" />
                <Input value={pair.value} onChange={(e) => updateEnvPair(i, 'value', e.target.value)}
                  placeholder="value..." type="password" className="font-mono flex-1" />
                <button onClick={() => removeEnvPair(i)}
                  className="rounded p-1 text-muted-foreground hover:text-destructive">
                  <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                    <path d="M3 3l8 8M11 3l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                  </svg>
                </button>
              </div>
            ))}
          </div>

          <Button onClick={handleCreate} disabled={creating || !id.trim() || (transport === 'stdio' ? !command.trim() : !url.trim())}>
            {creating ? 'Adding...' : 'Add MCP Server'}
          </Button>
        </div>
      )}

      {servers.length === 0 ? (
        <div className="py-12 text-center">
          <div className="text-4xl mb-3">&#128268;</div>
          <div className="text-sm text-muted-foreground">No MCP servers configured.</div>
          <div className="text-xs text-muted-foreground mt-2 max-w-md mx-auto space-y-1">
            <p><strong>stdio:</strong> <code className="text-primary">npx -y @modelcontextprotocol/server-github</code></p>
            <p><strong>HTTP:</strong> <code className="text-primary">http://localhost:3001/mcp</code></p>
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          {servers.map((server) => (
            <div key={server.id} className="rounded-lg border border-border p-4">
              <div className="flex items-center justify-between">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-foreground">{server.id}</span>
                    <span className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-medium uppercase ${
                      getTransportLabel(server) === 'HTTP' ? 'bg-blue-500/20 text-blue-400' : 'bg-emerald-500/20 text-emerald-400'
                    }`}>
                      {getTransportLabel(server)}
                    </span>
                    <span className={`inline-block h-2 w-2 rounded-full ${server.enabled ? 'bg-emerald-500' : 'bg-zinc-500'}`} />
                  </div>
                  <div className="mt-1 font-mono text-xs text-muted-foreground truncate">
                    {server.command ? `${server.command} ${(server.args || []).join(' ')}` : server.url || ''}
                  </div>
                </div>
                <button onClick={() => handleDelete(server.id)}
                  className="rounded p-1 text-muted-foreground hover:bg-destructive/20 hover:text-destructive">
                  <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
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
