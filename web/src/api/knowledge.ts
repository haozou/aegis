import { fetchApi } from './client'

export interface KnowledgeDoc {
  id: string
  agent_id: string
  name: string
  source_type: string
  source_url?: string
  content?: string | null
  chunk_count: number
  status: string
  error?: string
  created_at: string
}

export async function listKnowledge(agentId: string): Promise<{ documents: KnowledgeDoc[]; count: number }> {
  return fetchApi(`/api/agents/${agentId}/knowledge`)
}

export async function getKnowledgeDoc(agentId: string, docId: string): Promise<{ document: KnowledgeDoc }> {
  return fetchApi(`/api/agents/${agentId}/knowledge/${docId}`)
}

export async function addKnowledgeUrl(agentId: string, url: string, name?: string): Promise<{ document: KnowledgeDoc }> {
  return fetchApi(`/api/agents/${agentId}/knowledge/url`, {
    method: 'POST',
    body: JSON.stringify({ url, name: name || '' }),
  })
}

export async function addKnowledgeText(agentId: string, text: string, name?: string): Promise<{ document: KnowledgeDoc }> {
  return fetchApi(`/api/agents/${agentId}/knowledge/text`, {
    method: 'POST',
    body: JSON.stringify({ text, name: name || '' }),
  })
}

export async function uploadKnowledgeFile(agentId: string, file: File): Promise<{ document: KnowledgeDoc }> {
  const formData = new FormData()
  formData.append('file', file)

  const token = localStorage.getItem('aegis_access_token')
  const resp = await fetch(`/api/agents/${agentId}/knowledge/upload`, {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${token}` },
    body: formData,
  })
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: 'Upload failed' }))
    throw new Error(err.detail || 'Upload failed')
  }
  return resp.json()
}

export async function deleteKnowledge(agentId: string, docId: string): Promise<void> {
  return fetchApi(`/api/agents/${agentId}/knowledge/${docId}`, { method: 'DELETE' })
}

export async function updateKnowledge(agentId: string, docId: string, data: {
  name?: string
  text?: string
  refetch?: boolean
}): Promise<{ document: KnowledgeDoc }> {
  return fetchApi(`/api/agents/${agentId}/knowledge/${docId}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}
