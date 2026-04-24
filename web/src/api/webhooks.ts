import { fetchApi } from './client'

export interface Webhook {
  id: string
  agent_id: string
  slug: string
  name: string
  direction: 'inbound' | 'outbound'
  url: string | null
  events: string[]
  secret: string | null
  is_active: boolean
  created_at: string
}

export interface WebhookDelivery {
  id: string
  webhook_id: string
  direction: string
  payload: Record<string, unknown>
  response_text: string | null
  status_code: number | null
  error: string | null
  created_at: string
}

export async function listWebhooks(agentId: string): Promise<{ webhooks: Webhook[]; count: number }> {
  return fetchApi(`/api/agents/${agentId}/webhooks`)
}

export async function createWebhook(agentId: string, data: {
  name: string
  direction: 'inbound' | 'outbound'
  url?: string
  events?: string[]
}): Promise<{ webhook: Webhook; trigger_url: string | null }> {
  return fetchApi(`/api/agents/${agentId}/webhooks`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function deleteWebhook(agentId: string, webhookId: string): Promise<void> {
  return fetchApi(`/api/agents/${agentId}/webhooks/${webhookId}`, { method: 'DELETE' })
}

export async function listDeliveries(agentId: string, webhookId: string): Promise<{ deliveries: WebhookDelivery[] }> {
  return fetchApi(`/api/agents/${agentId}/webhooks/${webhookId}/deliveries`)
}
