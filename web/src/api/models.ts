import { fetchApi } from './client'

export interface ModelsResponse {
  models: string[]
  default: string
}

export async function listModels(): Promise<ModelsResponse> {
  return fetchApi<ModelsResponse>('/api/models')
}
