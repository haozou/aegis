# API Reference

## Authentication

All API endpoints (except health and auth) require a JWT token in the `Authorization` header:

```
Authorization: Bearer <access_token>
```

### Register

```http
POST /api/auth/register
Content-Type: application/json

{"username": "user", "password": "password"}
```

### Login

```http
POST /api/auth/login
Content-Type: application/json

{"username": "user", "password": "password"}
```

**Response:**
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer"
}
```

### OAuth Login

```http
GET /api/oauth/{provider}/login
```
Providers: `google`, `github`, `microsoft`

Redirects to the OAuth provider's authorization page. After consent, the callback returns JWT tokens.

---

## Agents

### List Agents

```http
GET /api/agents
```

### Create Agent

```http
POST /api/agents
Content-Type: application/json

{
  "name": "My Agent",
  "description": "A helpful assistant",
  "system_prompt": "You are a helpful assistant.",
  "provider": "anthropic",
  "model": "claude-sonnet-4-5",
  "temperature": 0.7,
  "max_tokens": 4096,
  "tools": ["bash", "web_fetch", "file_read", "file_write"],
  "mcp_servers": [
    {
      "id": "server1",
      "transport": "stdio",
      "command": "npx",
      "args": ["-y", "@some/mcp-server"]
    }
  ]
}
```

### Get / Update / Delete Agent

```http
GET    /api/agents/{agent_id}
PUT    /api/agents/{agent_id}
DELETE /api/agents/{agent_id}
```

---

## Conversations

### List Conversations

```http
GET /api/conversations?agent_id={agent_id}
```

### Get Conversation Messages

```http
GET /api/conversations/{conversation_id}/messages
```

### Delete Conversation

```http
DELETE /api/conversations/{conversation_id}
```

---

## Agent API (External Access)

For programmatic access to agents via API keys.

### Send Message

```http
POST /api/agents/{agent_id}/api/message
Authorization: Bearer <api_key>
Content-Type: application/json

{
  "message": "What is the weather today?",
  "conversation_id": "optional-existing-conversation"
}
```

**Response:**
```json
{
  "response": "I'll help you check the weather...",
  "conversation_id": "conv_abc123",
  "message_id": "msg_def456"
}
```

### Manage API Keys

```http
GET    /api/agents/{agent_id}/api-keys
POST   /api/agents/{agent_id}/api-keys    {"name": "My Key"}
DELETE /api/agents/{agent_id}/api-keys/{key_id}
```

---

## Knowledge Base

### Upload Document

```http
POST /api/knowledge/{agent_id}/upload
Content-Type: multipart/form-data

file=@document.pdf
```

### Add URL

```http
POST /api/knowledge/{agent_id}/url
Content-Type: application/json

{"url": "https://example.com/article"}
```

### List Documents

```http
GET /api/knowledge/{agent_id}/documents
```

### Delete Document

```http
DELETE /api/knowledge/{agent_id}/documents/{document_id}
```

---

## Scheduled Tasks

### Create Task

```http
POST /api/scheduled-tasks
Content-Type: application/json

{
  "agent_id": "agent_abc123",
  "name": "Daily Report",
  "cron_expression": "0 9 * * *",
  "message": "Generate the daily status report",
  "enabled": true
}
```

### List / Update / Delete

```http
GET    /api/scheduled-tasks?agent_id={agent_id}
PUT    /api/scheduled-tasks/{task_id}
DELETE /api/scheduled-tasks/{task_id}
```

---

## Webhooks

### Create Webhook

```http
POST /api/webhooks
Content-Type: application/json

{
  "agent_id": "agent_abc123",
  "name": "Slack Notification",
  "url": "https://hooks.slack.com/...",
  "events": ["message.done"],
  "enabled": true
}
```

### Inbound Webhook Trigger

```http
POST /api/webhooks/{webhook_id}/trigger
Content-Type: application/json

{"message": "Process this incoming data"}
```

---

## Channels

### Create Channel Connection

```http
POST /api/channels
Content-Type: application/json

{
  "agent_id": "agent_abc123",
  "channel_type": "discord",
  "name": "My Discord Bot",
  "config": {
    "bot_token": "..."
  },
  "active": true
}
```

Supported types: `discord`, `telegram`, `email`, `sms`, `wechat`

### List / Update / Delete

```http
GET    /api/channels?agent_id={agent_id}
PUT    /api/channels/{connection_id}
DELETE /api/channels/{connection_id}
```

---

## Models

### List Available Models

```http
GET /api/models
```

Returns all models available across registered LLM providers.

---

## Health

```http
GET /api/health
```

Returns server status, uptime, and component health.

---

## WebSocket Protocol

### Connection

```
WS /ws/agents/{agent_id}/chat
```

### Authentication

After connecting, send an auth message:

```json
{"type": "auth", "token": "<JWT access token>"}
```

Server responds with:
```json
{"type": "auth_ok", "user_id": "user_abc", "agent_id": "agent_xyz"}
```

### Sending Messages

```json
{
  "type": "message",
  "content": "Hello, agent!",
  "conversation_id": "conv_123",
  "attachments": []
}
```

Omit `conversation_id` to create a new conversation.

### Server Events

| Event | Description |
|-------|-------------|
| `conversation_created` | New conversation was created |
| `text_delta` | Streamed text chunk: `{"type": "text_delta", "text": "..."}` |
| `tool_start` | Tool invocation starting: `{"type": "tool_start", "tool_name": "bash", "tool_input": {...}}` |
| `tool_result` | Tool execution result: `{"type": "tool_result", "tool_output": "...", "is_error": false}` |
| `done` | Response complete: `{"type": "done", "message_id": "...", "usage": {...}}` |
| `error` | Error occurred: `{"type": "error", "error": "..."}` |
| `mcp_auth_required` | MCP server needs authentication |

### Stream Resilience

If the client disconnects during streaming, the agent continues processing in the background. The stream buffer is kept for 60 seconds. Reconnect and send:

```json
{"type": "resume", "conversation_id": "conv_123"}
```

### Cancel

```json
{"type": "cancel"}
```

### Keep-alive

```json
{"type": "ping"}
```
Server responds with `{"type": "pong"}`.
