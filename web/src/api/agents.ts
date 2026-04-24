import { fetchApi } from './client'
import type { Agent } from '@/types'

export async function listAgents(): Promise<{
  agents: Agent[]
  count: number
}> {
  return fetchApi('/api/agents')
}

export async function createAgent(data: {
  name: string
  description?: string
  provider?: string
  model?: string
  temperature?: number
  max_tokens?: number
  system_prompt?: string
  allowed_tools?: string[]
}): Promise<{ agent: Agent }> {
  return fetchApi('/api/agents', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function getAgent(id: string): Promise<{ agent: Agent }> {
  return fetchApi(`/api/agents/${id}`)
}

export async function updateAgent(
  id: string,
  data: Partial<Agent>,
): Promise<{ agent: Agent }> {
  return fetchApi(`/api/agents/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export async function deleteAgent(id: string): Promise<void> {
  return fetchApi(`/api/agents/${id}`, {
    method: 'DELETE',
  })
}

export async function cloneAgent(id: string): Promise<{ agent: Agent }> {
  return fetchApi(`/api/agents/${id}/clone`, { method: 'POST' })
}

export interface AgentUsage {
  agent_id: string
  total_tokens: number
  message_count: number
  conversation_count: number
  recent_tokens_7d: number
}

export async function getAgentUsage(id: string): Promise<AgentUsage> {
  return fetchApi(`/api/agents/${id}/usage`)
}
