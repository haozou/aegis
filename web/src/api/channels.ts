import { fetchApi } from './client'

export type ChannelType = 'discord' | 'email' | 'telegram' | 'sms' | 'wechat'

export interface ChannelConnection {
  id: string
  agent_id: string
  user_id: string
  channel_type: ChannelType
  name: string
  config: Record<string, string>
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface CreateChannelConnectionData {
  channel_type: ChannelType
  name?: string
  config: Record<string, string>
  is_active?: boolean
}

export interface UpdateChannelConnectionData {
  name?: string
  config?: Record<string, string>
  is_active?: boolean
}

export async function listChannelConnections(agentId: string): Promise<{
  connections: ChannelConnection[]
  count: number
}> {
  return fetchApi(`/api/agents/${agentId}/channels`)
}

export async function createChannelConnection(
  agentId: string,
  data: CreateChannelConnectionData,
): Promise<{ connection: ChannelConnection }> {
  return fetchApi(`/api/agents/${agentId}/channels`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function getChannelConnection(
  agentId: string,
  connectionId: string,
): Promise<{ connection: ChannelConnection }> {
  return fetchApi(`/api/agents/${agentId}/channels/${connectionId}`)
}

export async function updateChannelConnection(
  agentId: string,
  connectionId: string,
  data: UpdateChannelConnectionData,
): Promise<{ connection: ChannelConnection }> {
  return fetchApi(`/api/agents/${agentId}/channels/${connectionId}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export async function deleteChannelConnection(
  agentId: string,
  connectionId: string,
): Promise<void> {
  return fetchApi(`/api/agents/${agentId}/channels/${connectionId}`, {
    method: 'DELETE',
  })
}
