import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { listAgents } from '@/api/agents'
import {
  listKnowledge,
  addKnowledgeUrl,
  addKnowledgeText,
  uploadKnowledgeFile,
  deleteKnowledge,
  updateKnowledge,
  getKnowledgeDoc,
  type KnowledgeDoc,
} from '@/api/knowledge'
import type { Agent } from '@/types'

type KnowledgeRow = KnowledgeDoc & { _agentName: string }

const statusColor: Record<string, string> = {
  ready: 'bg-emerald-500/20 text-emerald-400',
  processing: 'bg-yellow-500/20 text-yellow-400',
  pending: 'bg-yellow-500/20 text-yellow-400',
  error: 'bg-destructive/20 text-destructive',
}

export function KnowledgePage() {
  const navigate = useNavigate()
  const [agents, setAgents] = useState<Agent[]>([])
  const [docs, setDocs] = useState<KnowledgeRow[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [selectedAgentId, setSelectedAgentId] = useState('')
  const [addMode, setAddMode] = useState<'url' | 'text' | 'file'>('url')
  const [url, setUrl] = useState('')
  const [text, setText] = useState('')
  const [name, setName] = useState('')
  const [adding, setAdding] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  // Edit state
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editName, setEditName] = useState('')
  const [editText, setEditText] = useState('')
  const [saving, setSaving] = useState(false)
  const [loadingContent, setLoadingContent] = useState(false)

  useEffect(() => {
    listAgents().then(({ agents: list }) => {
      setAgents(list)
      if (list[0]) setSelectedAgentId(list[0].id)
      Promise.allSettled(list.map(a => listKnowledge(a.id))).then(results => {
        const all: KnowledgeRow[] = []
        results.forEach((r, i) => {
          if (r.status === 'fulfilled') {
            r.value.documents.forEach(doc => all.push({ ...doc, _agentName: list[i].name }))
          }
        })
        setDocs(all)
        setLoading(false)
      })
    }).catch(() => setLoading(false))
  }, [])

  async function handleAddUrl() {
    if (!selectedAgentId || !url.trim()) return
    const agentName = agents.find(a => a.id === selectedAgentId)?.name ?? ''
    setAdding(true)
    try {
      const { document } = await addKnowledgeUrl(selectedAgentId, url.trim(), name.trim())
      setDocs(prev => [{ ...document, _agentName: agentName }, ...prev])
      setUrl(''); setName(''); setShowCreate(false)
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Failed to add URL')
    } finally { setAdding(false) }
  }

  async function handleAddText() {
    if (!selectedAgentId || !text.trim()) return
    const agentName = agents.find(a => a.id === selectedAgentId)?.name ?? ''
    setAdding(true)
    try {
      const { document } = await addKnowledgeText(selectedAgentId, text.trim(), name.trim())
      setDocs(prev => [{ ...document, _agentName: agentName }, ...prev])
      setText(''); setName(''); setShowCreate(false)
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Failed to add text')
    } finally { setAdding(false) }
  }

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file || !selectedAgentId) return
    const agentName = agents.find(a => a.id === selectedAgentId)?.name ?? ''
    setAdding(true)
    try {
      const { document } = await uploadKnowledgeFile(selectedAgentId, file)
      setDocs(prev => [{ ...document, _agentName: agentName }, ...prev])
      setShowCreate(false)
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Upload failed')
    } finally {
      setAdding(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  async function handleDelete(doc: KnowledgeRow) {
    if (!confirm('Delete this document?')) return
    try {
      await deleteKnowledge(doc.agent_id, doc.id)
      setDocs(prev => prev.filter(d => d.id !== doc.id))
      if (editingId === doc.id) setEditingId(null)
    } catch { /* ignore */ }
  }

  async function startEditing(doc: KnowledgeRow) {
    setEditingId(doc.id)
    setEditName(doc.name)
    setEditText('')
    if (doc.source_type === 'text' || doc.source_type === 'file') {
      setLoadingContent(true)
      try {
        const { document: full } = await getKnowledgeDoc(doc.agent_id, doc.id)
        setEditText(full.content || '')
      } catch { /* ignore */ } finally {
        setLoadingContent(false)
      }
    }
  }

  async function handleSaveEdit(doc: KnowledgeRow) {
    if (!editingId) return
    setSaving(true)
    try {
      const payload: { name?: string; text?: string } = {}
      if (editName.trim() !== doc.name) payload.name = editName.trim()
      if ((doc.source_type === 'text' || doc.source_type === 'file') && editText.trim()) {
        payload.text = editText.trim()
      }
      if (Object.keys(payload).length === 0) { setEditingId(null); return }
      const { document: updated } = await updateKnowledge(doc.agent_id, doc.id, payload)
      setDocs(prev => prev.map(d => d.id === doc.id ? { ...updated, _agentName: doc._agentName } : d))
      setEditingId(null)
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Update failed')
    } finally { setSaving(false) }
  }

  async function handleRefetch(doc: KnowledgeRow) {
    if (!doc.source_url) return
    setSaving(true)
    try {
      const { document: updated } = await updateKnowledge(doc.agent_id, doc.id, { refetch: true })
      setDocs(prev => prev.map(d => d.id === doc.id ? { ...updated, _agentName: doc._agentName } : d))
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Re-fetch failed')
    } finally { setSaving(false) }
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
            <span className="text-xl">🧠</span>
            <h1 className="text-base font-semibold text-foreground">Knowledge</h1>
            <span className="text-xs text-muted-foreground hidden sm:block">— all agents</span>
          </div>
          <Button size="sm" onClick={() => setShowCreate(v => !v)}>
            {showCreate ? 'Cancel' : '+ Add Knowledge'}
          </Button>
        </div>
      </header>

      <div className="mx-auto max-w-3xl px-4 py-6 space-y-4">
        {/* Create form */}
        {showCreate && (
          <div className="rounded-lg border border-border bg-card p-5 space-y-4">
            <h3 className="text-sm font-semibold text-foreground">Add Knowledge</h3>

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

            {/* Mode selector */}
            <div className="flex gap-1.5 flex-wrap">
              {(['url', 'text', 'file'] as const).map(mode => (
                <button
                  key={mode}
                  onClick={() => setAddMode(mode)}
                  className={`rounded-md px-3 py-1.5 text-sm transition-colors ${
                    addMode === mode
                      ? 'bg-primary text-primary-foreground'
                      : 'bg-muted text-muted-foreground hover:text-foreground'
                  }`}
                >
                  {mode === 'url' ? '🌐 URL' : mode === 'text' ? '📝 Text' : '📄 File'}
                </button>
              ))}
            </div>

            {/* URL mode */}
            {addMode === 'url' && (
              <div className="space-y-3">
                <div className="space-y-1.5">
                  <Label>URL</Label>
                  <Input value={url} onChange={e => setUrl(e.target.value)} placeholder="https://docs.example.com/guide" />
                </div>
                <div className="space-y-1.5">
                  <Label>Name (optional)</Label>
                  <Input value={name} onChange={e => setName(e.target.value)} placeholder="API Documentation" />
                </div>
                <Button size="sm" onClick={handleAddUrl} disabled={adding || !url.trim() || !selectedAgentId}>
                  {adding ? 'Adding…' : 'Add URL'}
                </Button>
              </div>
            )}

            {/* Text mode */}
            {addMode === 'text' && (
              <div className="space-y-3">
                <div className="space-y-1.5">
                  <Label>Name</Label>
                  <Input value={name} onChange={e => setName(e.target.value)} placeholder="Company policies" />
                </div>
                <div className="space-y-1.5">
                  <Label>Content</Label>
                  <textarea
                    value={text}
                    onChange={e => setText(e.target.value)}
                    rows={5}
                    placeholder="Paste text content here…"
                    className="flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                  />
                </div>
                <Button size="sm" onClick={handleAddText} disabled={adding || !text.trim() || !selectedAgentId}>
                  {adding ? 'Adding…' : 'Add Text'}
                </Button>
              </div>
            )}

            {/* File mode */}
            {addMode === 'file' && (
              <div className="space-y-3">
                <p className="text-xs text-muted-foreground">Supported formats: .txt, .md, .csv, .json, .py, .js, .ts, .html</p>
                <input
                  ref={fileRef}
                  type="file"
                  accept=".txt,.md,.csv,.json,.py,.js,.ts,.html"
                  className="hidden"
                  onChange={handleUpload}
                />
                <Button size="sm" onClick={() => fileRef.current?.click()} disabled={adding || !selectedAgentId}>
                  {adding ? 'Uploading…' : 'Choose File'}
                </Button>
              </div>
            )}
          </div>
        )}

        {/* List */}
        {loading ? (
          <div className="py-16 text-center text-sm text-muted-foreground">Loading…</div>
        ) : docs.length === 0 && !showCreate ? (
          <div className="py-16 text-center">
            <div className="text-5xl mb-4">📚</div>
            <p className="text-sm font-medium text-foreground">No knowledge documents yet</p>
            <p className="mt-1 text-xs text-muted-foreground">Add URLs, text, or upload files to build your agents' knowledge</p>
          </div>
        ) : (
          <div className="space-y-2">
            {docs.map(doc => (
              <div key={doc.id} className="rounded-lg border border-border bg-card">
                {editingId === doc.id ? (
                  /* Edit mode */
                  <div className="p-4 space-y-3">
                    <div className="flex items-center justify-between">
                      <h4 className="text-sm font-medium text-foreground">Edit Document</h4>
                      <button onClick={() => setEditingId(null)} className="text-xs text-muted-foreground hover:text-foreground">Cancel</button>
                    </div>
                    <div className="space-y-1.5">
                      <Label>Name</Label>
                      <Input value={editName} onChange={e => setEditName(e.target.value)} className="text-sm" />
                    </div>
                    {(doc.source_type === 'text' || doc.source_type === 'file') && (
                      <div className="space-y-1.5">
                        <Label>Content</Label>
                        {loadingContent ? (
                          <div className="flex items-center gap-2 py-4 text-xs text-muted-foreground">
                            <span className="h-3 w-3 rounded-full border-2 border-primary border-t-transparent animate-spin" />
                            Loading content…
                          </div>
                        ) : (
                          <textarea
                            value={editText}
                            onChange={e => setEditText(e.target.value)}
                            rows={8}
                            placeholder="Document content…"
                            className="flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                          />
                        )}
                      </div>
                    )}
                    {doc.source_type === 'url' && doc.source_url && (
                      <div className="flex items-center gap-2 text-xs text-muted-foreground">
                        <span className="truncate">Source: {doc.source_url}</span>
                        <button
                          onClick={() => handleRefetch(doc)}
                          disabled={saving}
                          className="shrink-0 rounded px-2 py-1 bg-muted hover:text-foreground transition-colors"
                        >
                          {saving ? 'Fetching…' : '🔄 Re-fetch'}
                        </button>
                      </div>
                    )}
                    <div className="flex gap-2">
                      <Button size="sm" onClick={() => handleSaveEdit(doc)} disabled={saving}>
                        {saving ? 'Saving…' : 'Save Changes'}
                      </Button>
                      <Button size="sm" variant="outline" onClick={() => setEditingId(null)}>Cancel</Button>
                    </div>
                  </div>
                ) : (
                  /* View mode */
                  <div className="flex items-center gap-3 px-4 py-3 group">
                    <span className="text-lg shrink-0">
                      {doc.source_type === 'url' ? '🌐' : doc.source_type === 'file' ? '📄' : '📝'}
                    </span>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-sm font-medium text-foreground truncate">{doc.name}</span>
                        <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-medium text-primary shrink-0">
                          {doc._agentName}
                        </span>
                      </div>
                      <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                        <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${statusColor[doc.status] ?? 'bg-muted text-muted-foreground'}`}>
                          {doc.status}
                        </span>
                        {doc.chunk_count > 0 && (
                          <span className="text-[10px] text-muted-foreground">{doc.chunk_count} chunks</span>
                        )}
                        {doc.source_url && (
                          <span className="text-[10px] text-muted-foreground truncate max-w-[220px]">{doc.source_url}</span>
                        )}
                        {doc.error && (
                          <span className="text-[10px] text-destructive truncate">{doc.error}</span>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-1 shrink-0 md:opacity-0 md:group-hover:opacity-100 transition-opacity">
                      <button
                        onClick={() => startEditing(doc)}
                        className="rounded px-2 py-1 text-xs bg-muted text-muted-foreground hover:text-foreground"
                      >
                        Edit
                      </button>
                      <button
                        onClick={() => handleDelete(doc)}
                        className="rounded p-1.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors"
                      >
                        <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
                          <path d="M3 3l8 8M11 3l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                        </svg>
                      </button>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
