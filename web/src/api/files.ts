import { getAccessToken } from './client'
import { ApiError } from './client'

export interface UploadedFile {
  file_id: string
  filename: string
  media_type: string
  size: number
}

/**
 * Upload a file to the server.
 * Uses raw fetch (not fetchApi) so we don't override Content-Type —
 * the browser must set the multipart/form-data boundary automatically.
 */
export async function uploadFile(file: File): Promise<UploadedFile> {
  const token = getAccessToken()
  const form = new FormData()
  form.append('file', file)

  const response = await fetch('/api/files', {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  })

  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: 'Upload failed' }))
    throw new ApiError(err.detail || 'Upload failed', response.status)
  }

  return response.json() as Promise<UploadedFile>
}

/**
 * Returns the URL for serving a previously uploaded file.
 * The endpoint requires auth via Authorization header.
 */
export function getFileUrl(fileId: string): string {
  return `/api/files/${fileId}`
}
