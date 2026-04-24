import { useState } from 'react'
import type { ToolCall } from '@/types'

export type { ToolCall }

const TOOL_ICONS: Record<string, string> = {
  web_search: '🔍',
  web_fetch: '🌐',
  bash: '⌨️',
  file_read: '📄',
  file_write: '✏️',
  file_list: '📁',
  manage_schedules: '⏰',
  knowledge_base: '📚',
  delegate_to_agent: '🤖',
}

const TOOL_LABELS: Record<string, string> = {
  web_search: 'Searched the web',
  web_fetch: 'Fetched a webpage',
  bash: 'Ran command',
  file_read: 'Read file',
  file_write: 'Wrote file',
  file_list: 'Listed directory',
  manage_schedules: 'Managed schedule',
  knowledge_base: 'Knowledge base',
  delegate_to_agent: 'Delegated to agent',
}

function getToolIcon(name: string): string {
  if (name.startsWith('mcp__')) return '🔌'
  return TOOL_ICONS[name] || '🔧'
}

function getToolLabel(name: string, input?: Record<string, unknown>): string {
  // MCP tools: mcp__serverId__toolName
  if (name.startsWith('mcp__')) {
    const parts = name.split('__')
    return `${parts[1]}: ${parts.slice(2).join('__')}`
  }
  const base = TOOL_LABELS[name] || name
  // Add context for certain tools
  if (name === 'web_search' && input?.query) return `Searched: "${input.query}"`
  if (name === 'bash' && input?.command) {
    const cmd = String(input.command)
    return `Ran: ${cmd.length > 60 ? cmd.slice(0, 57) + '...' : cmd}`
  }
  if (name === 'file_read' && input?.path) return `Read: ${String(input.path).split('/').pop()}`
  if (name === 'file_write' && input?.path) return `Wrote: ${String(input.path).split('/').pop()}`
  if (name === 'web_fetch' && input?.url) {
    const url = String(input.url)
    try { return `Fetched: ${new URL(url).hostname}` } catch { return `Fetched URL` }
  }
  if (name === 'delegate_to_agent' && input?.agent_name) return `Delegated to: ${input.agent_name}`
  if (name === 'knowledge_base' && input?.action) {
    if (input.action === 'search' && input.query) return `KB search: "${input.query}"`
    if (input.action === 'add_url' && input.url) return `KB add URL: ${input.url}`
    return `KB: ${input.action}`
  }
  if (name === 'manage_schedules' && input?.action) return `Schedule: ${input.action}`
  return base
}

function truncateOutput(text: string, maxLen = 800): string {
  if (text.length <= maxLen) return text
  return text.slice(0, maxLen) + '\n... (truncated)'
}

export function ToolCallBlock({ tool }: { tool: ToolCall }) {
  const [expanded, setExpanded] = useState(false)
  const icon = getToolIcon(tool.name)
  const label = getToolLabel(tool.name, tool.input)

  return (
    <div className="my-2 rounded-lg border border-border overflow-hidden text-[13px]">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-2 px-3 py-2.5 text-left hover:bg-muted/50 transition-colors"
      >
        <span className="text-sm shrink-0">{icon}</span>
        <span className="flex-1 min-w-0 truncate text-muted-foreground">
          {label}
        </span>
        {tool.status === 'running' && (
          <span className="shrink-0 h-3 w-3 rounded-full border-2 border-primary border-t-transparent animate-spin" />
        )}
        {tool.status === 'done' && (
          <span className="shrink-0 text-emerald-500 text-xs font-medium">Done</span>
        )}
        {tool.status === 'error' && (
          <span className="shrink-0 text-destructive text-xs font-medium">Error</span>
        )}
        <svg
          width="12" height="12" viewBox="0 0 12 12" fill="none"
          className={`shrink-0 text-muted-foreground transition-transform ${expanded ? 'rotate-180' : ''}`}
        >
          <path d="M3 4.5l3 3 3-3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>

      {expanded && (
        <div className="border-t border-border bg-muted/30">
          {/* Input */}
          {tool.input && Object.keys(tool.input).length > 0 && (
            <div className="px-3 py-2 border-b border-border">
              <div className="text-[11px] font-medium text-muted-foreground mb-1 uppercase tracking-wider">Input</div>
              <pre className="whitespace-pre-wrap break-all font-mono text-xs text-foreground/80 max-h-40 overflow-y-auto">
                {JSON.stringify(tool.input, null, 2)}
              </pre>
            </div>
          )}
          {/* Output */}
          {tool.output !== undefined && (
            <div className="px-3 py-2">
              <div className="text-[11px] font-medium text-muted-foreground mb-1 uppercase tracking-wider">Output</div>
              <pre className={`whitespace-pre-wrap break-all font-mono text-xs max-h-60 overflow-y-auto ${
                tool.isError ? 'text-destructive' : 'text-foreground/80'
              }`}>
                {truncateOutput(tool.output)}
              </pre>
              {/* Link to delegated agent's conversation */}
              {tool.name === 'delegate_to_agent' && tool.output && (() => {
                try {
                  const parsed = JSON.parse(tool.output)
                  if (parsed.agent_id && parsed.agent) {
                    return (
                      <a href={`/agents/${parsed.agent_id}`}
                        className="mt-2 inline-flex items-center gap-1 text-[10px] text-primary hover:underline"
                        onClick={(e) => e.stopPropagation()}>
                        View full conversation in {parsed.agent} →
                      </a>
                    )
                  }
                } catch { /* not JSON */ }
                return null
              })()}
            </div>
          )}
          {tool.status === 'running' && !tool.output && (
            <div className="px-3 py-2 text-muted-foreground italic">Running...</div>
          )}
        </div>
      )}
    </div>
  )
}

/** Renders a group of tool calls (used between text blocks) */
export function ToolCallGroup({ tools }: { tools: ToolCall[] }) {
  if (tools.length === 0) return null
  return (
    <div className="space-y-0.5">
      {tools.map((tool) => (
        <ToolCallBlock key={tool.id} tool={tool} />
      ))}
    </div>
  )
}
