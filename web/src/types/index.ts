export interface User {
  id: string
  email: string
  username: string
  display_name: string | null
  avatar_url: string | null
  plan: string
  is_active: boolean
  is_admin: boolean
  created_at: string
  updated_at: string
}

export interface TokenPair {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
}

export interface AuthResponse {
  user: User
  tokens: TokenPair
}

export interface Conversation {
  id: string
  title: string
  created_at: string
  updated_at: string
  provider: string
  model: string
  system_prompt: string | null
  user_id: string | null
  agent_id: string | null
  metadata: Record<string, unknown>
}

export interface Message {
  id: string
  conversation_id: string
  role: 'user' | 'assistant' | 'system' | 'tool'
  content: string | ContentPart[]
  tool_calls: ToolCall[] | null
  tool_call_id: string | null
  created_at: string
  tokens_used: number
  metadata: Record<string, unknown>
}

export interface ContentPart {
  type: string
  text?: string
  id?: string
  name?: string
  input?: Record<string, unknown>
  content?: unknown
  is_error?: boolean
  source?: {
    type: 'base64' | 'url'
    media_type: string
    data?: string
    url?: string
  }
}

export interface ToolCall {
  id: string
  name: string
  input?: Record<string, unknown>
  output?: string
  is_error?: boolean
  isError?: boolean
  status?: 'running' | 'done' | 'error'
}

export interface Agent {
  id: string
  user_id: string
  slug: string
  name: string
  description: string
  avatar_url: string | null
  status: 'draft' | 'active' | 'paused' | 'archived'
  is_public: boolean
  created_at: string
  updated_at: string
  provider: string
  model: string
  temperature: number
  max_tokens: number
  system_prompt: string
  enable_memory: boolean
  enable_skills: boolean
  max_tool_iterations: number
  allowed_tools: string[]
  metadata: Record<string, unknown>
}

export interface StreamEvent {
  type: 'session_ready' | 'text_delta' | 'tool_start' | 'tool_result' | 'done' | 'error' | 'cancelled'
  text?: string
  tool_name?: string
  tool_id?: string
  tool_input?: Record<string, unknown>
  tool_output?: string
  is_error?: boolean
  message_id?: string
  usage?: { input: number; output: number }
  error?: string
}

export interface WsMessage {
  type: string
  [key: string]: unknown
}
