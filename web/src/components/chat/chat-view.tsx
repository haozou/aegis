import { useEffect, useState, useCallback } from 'react'
import { MessageList } from './message-list'
import { ChatInput } from './chat-input'
import { listMessages } from '@/api/conversations'
import type { Message } from '@/types'

interface ChatViewProps {
  conversationId: string | null
}

export function ChatView({ conversationId }: ChatViewProps) {
  const [messages, setMessages] = useState<Message[]>([])
  const [loading, setLoading] = useState(false)

  const loadMessages = useCallback(async () => {
    if (!conversationId) {
      setMessages([])
      return
    }
    setLoading(true)
    try {
      const { messages: msgs } = await listMessages(conversationId)
      setMessages(msgs)
    } catch {
      // ignore
    } finally {
      setLoading(false)
    }
  }, [conversationId])

  useEffect(() => {
    loadMessages()
  }, [loadMessages])

  function handleSend(_message: string) {
    // TODO: In Phase 2, this will send through the agent worker pipeline
    // For now, just show the message was received
    if (!conversationId) return

    const tempMessage: Message = {
      id: `temp_${Date.now()}`,
      conversation_id: conversationId,
      role: 'user',
      content: _message,
      tool_calls: null,
      tool_call_id: null,
      created_at: new Date().toISOString(),
      tokens_used: 0,
      metadata: {},
    }
    setMessages((prev) => [...prev, tempMessage])
  }

  if (!conversationId) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <div className="text-center">
          <div className="text-6xl mb-6">&#9889;</div>
          <h2 className="text-2xl font-semibold text-foreground">Welcome to Aegis</h2>
          <p className="mt-2 text-muted-foreground">
            Select a conversation or create a new one to get started
          </p>
        </div>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <div className="text-muted-foreground">Loading messages...</div>
      </div>
    )
  }

  return (
    <div className="flex flex-1 flex-col">
      <MessageList messages={messages} />
      <ChatInput onSend={handleSend} />
    </div>
  )
}
