import type { Message } from '@/types'

function getTextContent(message: Message): string {
  if (typeof message.content === 'string') {
    return message.content
  }
  return message.content
    .filter((p) => p.type === 'text' && p.text)
    .map((p) => p.text!)
    .join('\n')
}

interface MessageBubbleProps {
  message: Message
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === 'user'
  const text = getTextContent(message)

  if (!text) return null

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[80%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
          isUser
            ? 'bg-primary text-primary-foreground'
            : 'bg-muted text-foreground'
        }`}
      >
        <div className="whitespace-pre-wrap break-words">{text}</div>
        <div
          className={`mt-1 text-[10px] ${
            isUser ? 'text-primary-foreground/60' : 'text-muted-foreground'
          }`}
        >
          {new Date(message.created_at).toLocaleTimeString([], {
            hour: '2-digit',
            minute: '2-digit',
          })}
        </div>
      </div>
    </div>
  )
}
