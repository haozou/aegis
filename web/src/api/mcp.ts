import { fetchApi } from './client'

export interface MCPServer {
  id: string
  transport?: 'stdio' | 'http'
  command?: string
  args?: string[]
  env?: Record<string, string>
  url?: string
  headers?: Record<string, string>
  enabled: boolean
  enabled_tools?: string[]
  oauth_token?: string
  oauth_client_id?: string
}

export interface MCPToolInfo {
  name: string
  description: string
  input_schema: Record<string, unknown>
}

export async function listMCPServers(agentId: string): Promise<{ mcp_servers: MCPServer[]; count: number }> {
  return fetchApi(`/api/agents/${agentId}/mcp-servers`)
}

export async function addMCPServer(agentId: string, data: MCPServer): Promise<{ mcp_servers: MCPServer[] }> {
  return fetchApi(`/api/agents/${agentId}/mcp-servers`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function removeMCPServer(agentId: string, serverId: string): Promise<void> {
  return fetchApi(`/api/agents/${agentId}/mcp-servers/${serverId}`, { method: 'DELETE' })
}

export async function probeMCPServer(agentId: string, data: {
  command?: string
  args?: string[]
  env?: Record<string, string>
  url?: string
  headers?: Record<string, string>
  transport?: string
  oauth_token?: string
}): Promise<{ tools: MCPToolInfo[]; count: number }> {
  return fetchApi(`/api/agents/${agentId}/mcp-probe`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function updateMCPServer(
  agentId: string,
  serverId: string,
  data: {
    command?: string
    args?: string[]
    env?: Record<string, string>
    url?: string
    enabled?: boolean
  },
): Promise<{ mcp_servers: MCPServer[] }> {
  return fetchApi(`/api/agents/${agentId}/mcp-servers/${serverId}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export async function updateMCPServerTools(
  agentId: string,
  serverId: string,
  enabledTools: string[],
): Promise<{ mcp_servers: MCPServer[]; count: number }> {
  return fetchApi(`/api/agents/${agentId}/mcp-servers/${serverId}/tools`, {
    method: 'PATCH',
    body: JSON.stringify({ enabled_tools: enabledTools }),
  })
}
