# Tools

Aegis agents can use tools to interact with the outside world. Tools are invoked autonomously by the LLM during the agentic tool loop.

## Built-in Tools

### Shell & Code Execution

| Tool | Description |
|------|-------------|
| `bash` | Execute shell commands. Sandboxed with configurable timeout (default 30s) and output limit (50KB). |
| `python_interpreter` | Persistent stateful Python REPL. Supports data science libraries (pandas, numpy, matplotlib). Auto-saves generated plots. Timeout: 120s. |

### Web

| Tool | Description |
|------|-------------|
| `web_fetch` | Fetch web pages and convert HTML to Markdown. Max 20K characters. |
| `web_search` | Search the web via DuckDuckGo. Returns titles, URLs, and snippets. |

### File Operations

| Tool | Description |
|------|-------------|
| `file_read` | Read files within allowed paths. Max 1MB. |
| `file_write` | Write/create files within allowed paths. |
| `file_list` | List directory contents. |
| `file_export` | Make sandbox files downloadable via the file API. |

### Document Export

| Tool | Description |
|------|-------------|
| `document_export` | Export content to PDF, DOCX, or Markdown files. |

### Image Generation

| Tool | Description |
|------|-------------|
| `image_generate` | Generate images via DALL-E (OpenAI-compatible API). |

### Video Editing

| Tool | Description |
|------|-------------|
| `video_probe` | Inspect video metadata using ffprobe. |
| `video_cut` | Cut/trim video segments. |
| `video_concat` | Concatenate multiple videos. |
| `video_add_audio` | Add an audio track to a video. |
| `video_thumbnail` | Extract a thumbnail frame from video. |
| `video_export` | Export/transcode video to different formats. |
| `video_overlay_text` | Overlay text on video. |
| `video_speed` | Change video playback speed. |

### Knowledge Base

| Tool | Description |
|------|-------------|
| `knowledge_base` | Search, add, list, or delete from the agent's knowledge base. Actions: `search`, `add_url`, `add_text`, `list`, `delete`. |

### Scheduling

| Tool | Description |
|------|-------------|
| `manage_schedules` | Create, list, or delete cron-scheduled agent tasks. |

### Agent Delegation

| Tool | Description |
|------|-------------|
| `delegate_to_agent` | Delegate a task to another agent owned by the same user. Max recursion depth: 3. |

## Tool Configuration

Tools can be enabled/disabled globally via environment variables:

```env
TOOLS__BASH_ENABLED=true
TOOLS__WEB_FETCH_ENABLED=true
TOOLS__FILE_OPS_ENABLED=true
TOOLS__VIDEO_ENABLED=true
TOOLS__IMAGE_GEN_ENABLED=true
TOOLS__DOCUMENT_EXPORT_ENABLED=true
TOOLS__PYTHON_INTERPRETER_ENABLED=true
```

Per-agent tool selection is configured when creating an agent — set the `tools` array to limit which tools the agent can use.

## File Sandbox

File operations are restricted to paths listed in `TOOLS__ALLOWED_PATHS` (default: `data/sandbox` and home directory). The primary sandbox is `data/sandbox`, which is also used by the Python interpreter for saving outputs.

## MCP (Model Context Protocol)

Aegis includes an MCP client that can connect to external tool servers.

### Supported Transports

- **stdio** — Launch a local process (e.g., `npx -y @some/mcp-server`)
- **HTTP + SSE** — Connect to a remote MCP server via URL

### Configuration

MCP servers are configured per-agent:

```json
{
  "mcp_servers": [
    {
      "id": "filesystem",
      "transport": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path"]
    },
    {
      "id": "remote-tools",
      "transport": "sse",
      "url": "https://mcp.example.com/sse",
      "headers": {"Authorization": "Bearer ..."}
    }
  ]
}
```

MCP tools appear in the agent's tool list with names prefixed `mcp__{server_id}__{tool_name}`.

### Authentication

The MCP client supports OAuth/device code authentication flows. When an MCP server requires auth, the client sends an `mcp_auth_required` WebSocket event to the frontend, which can guide the user through the login process.

## Creating Custom Tools

Extend `BaseTool` to create a custom tool:

```python
from aegis.tools.base import BaseTool
from aegis.tools.types import ToolContext, ToolResult

class MyTool(BaseTool):
    @property
    def name(self) -> str:
        return "my_tool"

    @property
    def description(self) -> str:
        return "Description shown to the LLM"

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query"
                }
            },
            "required": ["query"]
        }

    async def execute(self, context: ToolContext, **kwargs) -> ToolResult:
        query = kwargs["query"]
        # ... do work ...
        return ToolResult(output="Result text", is_error=False)
```

Register it in the tool registry during app startup.
