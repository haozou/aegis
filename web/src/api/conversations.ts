import { fetchApi } from './client'
import type { Conversation, Message } from '@/types'

export async function listConversations(): Promise<{
  conversations: Conversation[]
  count: number
}> {
  return fetchApi('/api/conversations')
}

export async function createConversation(
  title: string = 'New Conversation',
): Promise<{ conversation: Conversation }> {
  return fetchApi('/api/conversations', {
    method: 'POST',
    body: JSON.stringify({ title }),
  })
}

export async function getConversation(
  id: string,
): Promise<{ conversation: Conversation }> {
  return fetchApi(`/api/conversations/${id}`)
}

export async function updateConversation(
  id: string,
  data: { title?: string },
): Promise<{ conversation: Conversation }> {
  return fetchApi(`/api/conversations/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export async function deleteConversation(id: string): Promise<void> {
  return fetchApi(`/api/conversations/${id}`, {
    method: 'DELETE',
  })
}

export async function listMessages(
  conversationId: string,
): Promise<{ messages: Message[]; count: number }> {
  return fetchApi(`/api/conversations/${conversationId}/messages`)
}

export async function deleteMessagesAfter(
  conversationId: string,
  messageId: string,
): Promise<void> {
  return fetchApi(`/api/conversations/${conversationId}/messages/after/${messageId}`, {
    method: 'DELETE',
  })
}
