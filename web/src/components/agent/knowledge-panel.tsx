import { useState, useEffect, useRef } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { listKnowledge, addKnowledgeUrl, addKnowledgeText, uploadKnowledgeFile, deleteKnowledge, updateKnowledge, getKnowledgeDoc, type KnowledgeDoc } from '@/api/knowledge'

interface Props { agentId: string }

export function KnowledgePanel({ agentId }: Props) {
  const [docs, setDocs] = useState<KnowledgeDoc[]>([])
  const [loading, setLoading] = useState(true)
  const [addMode, setAddMode] = useState<'url' | 'text' | null>(null)
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
    listKnowledge(agentId).then(({ documents }) => setDocs(documents)).catch(() => {}).finally(() => setLoading(false))
  }, [agentId])

  async function handleAddUrl() {
    if (!url.trim()) return
    setAdding(true)
    try {
      const { document } = await addKnowledgeUrl(agentId, url.trim(), name.trim())
      setDocs(prev => [document, ...prev])
      setUrl(''); setName(''); setAddMode(null)
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Failed to add URL')
    } finally { setAdding(false) }
  }

  async function handleAddText() {
    if (!text.trim()) return
    setAdding(true)
    try {
      const { document } = await addKnowledgeText(agentId, text.trim(), name.trim())
      setDocs(prev => [document, ...prev])
      setText(''); setName(''); setAddMode(null)
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Failed to add text')
    } finally { setAdding(false) }
  }

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setAdding(true)
    try {
      const { document } = await uploadKnowledgeFile(agentId, file)
      setDocs(prev => [document, ...prev])
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Upload failed')
    } finally {
      setAdding(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  async function handleDelete(docId: string) {
    if (!confirm('Delete this document?')) return
    try {
      await deleteKnowledge(agentId, docId)
      setDocs(prev => prev.filter(d => d.id !== docId))
      if (editingId === docId) setEditingId(null)
    } catch { /* ignore */ }
  }

  async function startEditing(doc: KnowledgeDoc) {
    setEditingId(doc.id)
    setEditName(doc.name)
    setEditText('')
    // Fetch full content from server
    if (doc.source_type === 'text' || doc.source_type === 'file') {
      setLoadingContent(true)
      try {
        const { document: full } = await getKnowledgeDoc(agentId, doc.id)
        setEditText(full.content || '')
      } catch { /* ignore */ } finally {
        setLoadingContent(false)
      }
    }
  }

  async function handleSaveEdit(doc: KnowledgeDoc) {
    if (!editingId) return
    setSaving(true)
    try {
      const payload: { name?: string; text?: string } = {}
      if (editName.trim() !== doc.name) payload.name = editName.trim()
      // For text/file docs, send text if it's non-empty (content was loaded from server)
      if ((doc.source_type === 'text' || doc.source_type === 'file') && editText.trim()) {
        payload.text = editText.trim()
      }

      if (Object.keys(payload).length === 0) {
        setEditingId(null)
        return
      }

      const { document: updated } = await updateKnowledge(agentId, doc.id, payload)
      setDocs(prev => prev.map(d => d.id === doc.id ? updated : d))
      setEditingId(null)
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Update failed')
    } finally { setSaving(false) }
  }

  async function handleRefetch(doc: KnowledgeDoc) {
    if (!doc.source_url) return
    setSaving(true)
    try {
      const { document: updated } = await updateKnowledge(agentId, doc.id, { refetch: true })
      setDocs(prev => prev.map(d => d.id === doc.id ? updated : d))
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Re-fetch failed')
    } finally { setSaving(false) }
  }

  const statusColor: Record<string, string> = {
    ready: 'bg-emerald-500/20 text-emerald-400',
    processing: 'bg-yellow-500/20 text-yellow-400',
    pending: 'bg-yellow-500/20 text-yellow-400',
    error: 'bg-destructive/20 text-destructive',
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-foreground">Knowledge Base</h2>
          <p className="text-xs text-muted-foreground mt-0.5">Add documents, URLs, or text for the agent to learn from</p>
        </div>
        <span className="text-xs text-muted-foreground">{docs.length} documents</span>
      </div>

      {/* Add buttons */}
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="outline" onClick={() => setAddMode(addMode === 'url' ? null : 'url')}>
          🌐 Add URL
        </Button>
        <Button size="sm" variant="outline" onClick={() => setAddMode(addMode === 'text' ? null : 'text')}>
          📝 Add Text
        </Button>
        <Button size="sm" variant="outline" onClick={() => fileRef.current?.click()} disabled={adding}>
          📄 Upload File
        </Button>
        <input ref={fileRef} type="file" accept=".txt,.md,.csv,.json,.py,.js,.ts,.html" className="hidden" onChange={handleUpload} />
      </div>

      {/* Add URL form */}
      {addMode === 'url' && (
        <div className="space-y-3 rounded-lg border border-primary/30 p-4">
          <div className="space-y-1">
            <Label className="text-xs">URL</Label>
            <Input value={url} onChange={e => setUrl(e.target.value)} placeholder="https://docs.example.com/guide" className="text-xs" />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Name (optional)</Label>
            <Input value={name} onChange={e => setName(e.target.value)} placeholder="API Documentation" className="text-xs" />
          </div>
          <div className="flex gap-2">
            <Button size="sm" onClick={handleAddUrl} disabled={adding || !url.trim()}>
              {adding ? 'Adding...' : 'Add URL'}
            </Button>
            <Button size="sm" variant="outline" onClick={() => setAddMode(null)}>Cancel</Button>
          </div>
        </div>
      )}

      {/* Add Text form */}
      {addMode === 'text' && (
        <div className="space-y-3 rounded-lg border border-primary/30 p-4">
          <div className="space-y-1">
            <Label className="text-xs">Name</Label>
            <Input value={name} onChange={e => setName(e.target.value)} placeholder="Company policies" className="text-xs" />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Content</Label>
            <textarea value={text} onChange={e => setText(e.target.value)} rows={6} placeholder="Paste text content here..."
              className="flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring" />
          </div>
          <div className="flex gap-2">
            <Button size="sm" onClick={handleAddText} disabled={adding || !text.trim()}>
              {adding ? 'Adding...' : 'Add Text'}
            </Button>
            <Button size="sm" variant="outline" onClick={() => setAddMode(null)}>Cancel</Button>
          </div>
        </div>
      )}

      {/* Document list */}
      {loading ? (
        <div className="text-center text-sm text-muted-foreground py-8">Loading...</div>
      ) : docs.length === 0 ? (
        <div className="text-center py-12">
          <div className="text-4xl mb-3">📚</div>
          <p className="text-sm text-muted-foreground">No documents yet</p>
          <p className="text-xs text-muted-foreground mt-1">Add URLs, text, or upload files to build the agent's knowledge</p>
        </div>
      ) : (
        <div className="space-y-2">
          {docs.map(doc => (
            <div key={doc.id} className="rounded-lg border border-border">
              {editingId === doc.id ? (
                /* ── Edit mode ── */
                <div className="p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <h4 className="text-sm font-medium text-foreground">Edit Document</h4>
                    <button onClick={() => setEditingId(null)} className="text-xs text-muted-foreground hover:text-foreground">
                      Cancel
                    </button>
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs">Name</Label>
                    <Input value={editName} onChange={e => setEditName(e.target.value)} className="text-xs" />
                  </div>
                  {(doc.source_type === 'text' || doc.source_type === 'file') && (
                    <div className="space-y-1">
                      <Label className="text-xs">Content</Label>
                      {loadingContent ? (
                        <div className="flex items-center gap-2 py-4 text-xs text-muted-foreground">
                          <span className="h-3 w-3 rounded-full border-2 border-primary border-t-transparent animate-spin" />
                          Loading content...
                        </div>
                      ) : (
                        <textarea
                          value={editText}
                          onChange={e => setEditText(e.target.value)}
                          rows={8}
                          placeholder="Document content..."
                          className="flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                        />
                      )}
                    </div>
                  )}
                  {doc.source_type === 'url' && doc.source_url && (
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <span>Source: {doc.source_url}</span>
                      <button
                        onClick={() => handleRefetch(doc)}
                        disabled={saving}
                        className="rounded px-2 py-1 bg-muted hover:text-foreground transition-colors"
                      >
                        {saving ? 'Fetching...' : '🔄 Re-fetch'}
                      </button>
                    </div>
                  )}
                  <div className="flex gap-2">
                    <Button size="sm" onClick={() => handleSaveEdit(doc)} disabled={saving}>
                      {saving ? 'Saving...' : 'Save Changes'}
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => setEditingId(null)}>Cancel</Button>
                  </div>
                </div>
              ) : (
                /* ── View mode ── */
                <div className="flex items-center gap-3 p-3 group">
                  <div className="text-lg shrink-0">
                    {doc.source_type === 'url' ? '🌐' : doc.source_type === 'file' ? '📄' : '📝'}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-foreground truncate">{doc.name}</div>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${statusColor[doc.status] || 'bg-muted text-muted-foreground'}`}>
                        {doc.status}
                      </span>
                      {doc.chunk_count > 0 && (
                        <span className="text-[10px] text-muted-foreground">{doc.chunk_count} chunks</span>
                      )}
                      {doc.source_url && (
                        <span className="text-[10px] text-muted-foreground truncate max-w-[200px]">{doc.source_url}</span>
                      )}
                      {doc.error && (
                        <span className="text-[10px] text-destructive truncate">{doc.error}</span>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-1 shrink-0 md:opacity-0 md:group-hover:opacity-100 transition-opacity">
                    <button
                      onClick={() => startEditing(doc)}
                      className="rounded px-2 py-1 text-xs text-muted-foreground hover:text-foreground bg-muted/50 hover:bg-muted"
                      title="Edit document"
                    >
                      Edit
                    </button>
                    <button onClick={() => handleDelete(doc.id)}
                      className="rounded p-1 text-muted-foreground/40 hover:bg-destructive/20 hover:text-destructive">
                      <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
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
  )
}
