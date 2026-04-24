import { useState, useMemo } from 'react'
import { getAccessToken } from '@/api/client'

export interface Artifact {
  id: string
  type: 'code' | 'file' | 'html'
  title: string
  language?: string
  content?: string           // code / html source
  url?: string               // /api/files/... for downloadable files
  filename?: string
  mime?: string
}

interface Props {
  artifact: Artifact
  onClose: () => void
}

export function ArtifactsPanel({ artifact, onClose }: Props) {
  const [copied, setCopied] = useState(false)
  const [htmlMode, setHtmlMode] = useState<'preview' | 'source'>('preview')

  const tokenizedUrl = useMemo(() => {
    if (!artifact.url) return null
    const tok = getAccessToken()
    return tok ? `${artifact.url}?token=${tok}` : artifact.url
  }, [artifact.url])

  const fileKind = useMemo(() => {
    const name = (artifact.filename || artifact.url || '').toLowerCase()
    if (/\.(png|jpe?g|gif|webp|svg|bmp)$/.test(name)) return 'image'
    if (name.endsWith('.pdf')) return 'pdf'
    if (/\.(md|markdown|txt|log|json|csv|ya?ml)$/.test(name)) return 'text'
    return 'binary'
  }, [artifact.filename, artifact.url])

  function copy() {
    if (!artifact.content) return
    navigator.clipboard.writeText(artifact.content)
    setCopied(true)
    setTimeout(() => setCopied(false), 1200)
  }

  function download() {
    if (artifact.url && tokenizedUrl) {
      window.open(tokenizedUrl, '_blank')
      return
    }
    if (artifact.content) {
      const blob = new Blob([artifact.content], { type: 'text/plain' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = artifact.filename || `artifact.${artifact.language || 'txt'}`
      a.click()
      URL.revokeObjectURL(url)
    }
  }

  return (
    <div className="flex h-full flex-col bg-sidebar">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <div className="flex items-center gap-2 min-w-0">
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" className="text-primary/70 shrink-0">
            <rect x="2" y="1.5" width="9" height="13" rx="1.5" stroke="currentColor" strokeWidth="1.3"/>
            <path d="M11 4l3 3v7.5a.5.5 0 01-.5.5H5" stroke="currentColor" strokeWidth="1.3"/>
          </svg>
          <span className="truncate text-sm font-medium text-foreground">{artifact.title}</span>
          {artifact.language && (
            <span className="shrink-0 rounded-full bg-muted px-1.5 py-0.5 text-[10px] font-mono text-muted-foreground">
              {artifact.language}
            </span>
          )}
        </div>
        <div className="flex items-center gap-0.5">
          {artifact.type === 'html' && (
            <button
              onClick={() => setHtmlMode(htmlMode === 'preview' ? 'source' : 'preview')}
              className="rounded p-1.5 text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
              title={htmlMode === 'preview' ? 'View source' : 'View preview'}
            >
              <span className="text-[10px] font-mono">{htmlMode === 'preview' ? '</>' : '👁'}</span>
            </button>
          )}
          {artifact.content && (
            <button
              onClick={copy}
              className="rounded p-1.5 text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
              title="Copy"
            >
              {copied ? (
                <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
                  <path d="M2 7l3.5 3.5 6.5-7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              ) : (
                <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
                  <rect x="4" y="4" width="8" height="8" rx="1.5" stroke="currentColor" strokeWidth="1.3"/>
                  <path d="M10 4V3a1.5 1.5 0 00-1.5-1.5H3A1.5 1.5 0 001.5 3v5.5A1.5 1.5 0 003 10h1" stroke="currentColor" strokeWidth="1.3"/>
                </svg>
              )}
            </button>
          )}
          <button
            onClick={download}
            className="rounded p-1.5 text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
            title="Download"
          >
            <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
              <path d="M7 1v8M3.5 6L7 9.5 10.5 6M2 12h10" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </button>
          <button
            onClick={onClose}
            className="rounded p-1.5 text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
            title="Close"
          >
            <svg width="13" height="13" viewBox="0 0 14 14" fill="none"><path d="M3 3l8 8M11 3l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
          </button>
        </div>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-auto">
        {artifact.type === 'code' && (
          <pre className="m-0 p-4 text-[12.5px] leading-[1.55] font-mono text-foreground whitespace-pre">
            <code>{artifact.content}</code>
          </pre>
        )}

        {artifact.type === 'html' && htmlMode === 'preview' && (
          <iframe
            title={artifact.title}
            srcDoc={artifact.content}
            sandbox="allow-scripts"
            className="h-full w-full border-0 bg-white"
          />
        )}
        {artifact.type === 'html' && htmlMode === 'source' && (
          <pre className="m-0 p-4 text-[12.5px] leading-[1.55] font-mono text-foreground whitespace-pre">
            <code>{artifact.content}</code>
          </pre>
        )}

        {artifact.type === 'file' && tokenizedUrl && (
          <>
            {fileKind === 'image' && (
              <div className="flex items-center justify-center p-4 bg-background/50 h-full">
                <img src={tokenizedUrl} alt={artifact.title} className="max-h-full max-w-full rounded object-contain" />
              </div>
            )}
            {fileKind === 'pdf' && (
              <iframe
                title={artifact.title}
                src={tokenizedUrl}
                className="h-full w-full border-0 bg-white"
              />
            )}
            {fileKind === 'text' && (
              <iframe
                title={artifact.title}
                src={tokenizedUrl}
                className="h-full w-full border-0 bg-background"
              />
            )}
            {fileKind === 'binary' && (
              <div className="flex flex-col items-center justify-center py-12 text-center px-4">
                <svg width="40" height="40" viewBox="0 0 16 16" fill="none" className="text-muted-foreground/40 mb-3">
                  <rect x="2" y="1.5" width="9" height="13" rx="1.5" stroke="currentColor" strokeWidth="1.3"/>
                  <path d="M11 4l3 3v7.5a.5.5 0 01-.5.5H5" stroke="currentColor" strokeWidth="1.3"/>
                </svg>
                <p className="text-sm text-muted-foreground mb-3">{artifact.filename || 'File'}</p>
                <button
                  onClick={download}
                  className="rounded-md bg-primary px-3 py-1.5 text-xs text-primary-foreground hover:bg-primary/90 transition-colors"
                >
                  Download
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
