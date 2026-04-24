import { fetchApi } from './client'

export interface Schedule {
  id: string
  agent_id: string
  name: string
  cron_expr: string
  prompt: string
  timezone: string
  is_active: boolean
  last_run: string | null
  next_run: string | null
  created_at: string
}

export interface TaskRun {
  id: string
  task_id: string
  conversation_id: string | null
  status: string
  response: string | null
  error: string | null
  tokens_used: number
  started_at: string
  completed_at: string | null
}

export async function listSchedules(agentId: string): Promise<{ schedules: Schedule[]; count: number }> {
  return fetchApi(`/api/agents/${agentId}/schedules`)
}

export async function createSchedule(agentId: string, data: {
  name: string
  cron_expr: string
  prompt: string
  timezone?: string
}): Promise<{ schedule: Schedule }> {
  return fetchApi(`/api/agents/${agentId}/schedules`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function deleteSchedule(agentId: string, taskId: string): Promise<void> {
  return fetchApi(`/api/agents/${agentId}/schedules/${taskId}`, { method: 'DELETE' })
}

export async function toggleSchedule(agentId: string, taskId: string, isActive: boolean): Promise<{ schedule: Schedule }> {
  return fetchApi(`/api/agents/${agentId}/schedules/${taskId}`, {
    method: 'PATCH',
    body: JSON.stringify({ is_active: isActive }),
  })
}

export async function updateSchedule(agentId: string, taskId: string, data: {
  name?: string
  cron_expr?: string
  prompt?: string
  is_active?: boolean
}): Promise<{ schedule: Schedule }> {
  return fetchApi(`/api/agents/${agentId}/schedules/${taskId}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export async function listRuns(agentId: string, taskId: string): Promise<{ runs: TaskRun[] }> {
  return fetchApi(`/api/agents/${agentId}/schedules/${taskId}/runs`)
}
