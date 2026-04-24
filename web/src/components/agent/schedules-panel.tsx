import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { listSchedules, createSchedule, deleteSchedule, toggleSchedule, updateSchedule, listRuns, type Schedule, type TaskRun } from '@/api/schedules'

const CRON_PRESETS = [
  { label: 'Every minute', expr: '* * * * *' },
  { label: 'Every 5 minutes', expr: '*/5 * * * *' },
  { label: 'Every hour', expr: '0 * * * *' },
  { label: 'Daily at 9am', expr: '0 9 * * *' },
  { label: 'Daily at midnight', expr: '0 0 * * *' },
  { label: 'Weekdays at 9am', expr: '0 9 * * 1-5' },
  { label: 'Weekly (Mon 9am)', expr: '0 9 * * 1' },
]

interface Props {
  agentId: string
}

export function SchedulesPanel({ agentId }: Props) {
  const [schedules, setSchedules] = useState<Schedule[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [name, setName] = useState('')
  const [cronExpr, setCronExpr] = useState('0 9 * * *')
  const [prompt, setPrompt] = useState('')
  const [creating, setCreating] = useState(false)
  const [expandedTask, setExpandedTask] = useState<string | null>(null)
  const [runs, setRuns] = useState<Record<string, TaskRun[]>>({})
  const [loadingRuns, setLoadingRuns] = useState<string | null>(null)

  // Edit state
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editName, setEditName] = useState('')
  const [editCron, setEditCron] = useState('')
  const [editPrompt, setEditPrompt] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    loadSchedules()
  }, [agentId])

  async function loadSchedules() {
    try {
      const { schedules: s } = await listSchedules(agentId)
      setSchedules(s)
    } catch { /* ignore */ } finally {
      setLoading(false)
    }
  }

  async function handleCreate() {
    if (!cronExpr.trim() || !prompt.trim()) return
    setCreating(true)
    try {
      const { schedule } = await createSchedule(agentId, {
        name: name.trim(),
        cron_expr: cronExpr.trim(),
        prompt: prompt.trim(),
      })
      setSchedules((prev) => [schedule, ...prev])
      setName('')
      setPrompt('')
      setCronExpr('0 9 * * *')
      setShowCreate(false)
    } catch { /* ignore */ } finally {
      setCreating(false)
    }
  }

  async function handleDelete(taskId: string) {
    if (!confirm('Delete this schedule?')) return
    try {
      await deleteSchedule(agentId, taskId)
      setSchedules((prev) => prev.filter((s) => s.id !== taskId))
      if (editingId === taskId) setEditingId(null)
    } catch { /* ignore */ }
  }

  async function handleToggle(taskId: string, current: boolean) {
    try {
      const { schedule } = await toggleSchedule(agentId, taskId, !current)
      setSchedules((prev) => prev.map((s) => s.id === taskId ? schedule : s))
    } catch { /* ignore */ }
  }

  function startEditing(sched: Schedule) {
    setEditingId(sched.id)
    setEditName(sched.name)
    setEditCron(sched.cron_expr)
    setEditPrompt(sched.prompt)
  }

  function cancelEditing() {
    setEditingId(null)
  }

  async function handleSaveEdit() {
    if (!editingId || !editCron.trim() || !editPrompt.trim()) return
    setSaving(true)
    try {
      const { schedule } = await updateSchedule(agentId, editingId, {
        name: editName.trim(),
        cron_expr: editCron.trim(),
        prompt: editPrompt.trim(),
      })
      setSchedules((prev) => prev.map((s) => s.id === editingId ? schedule : s))
      setEditingId(null)
    } catch { /* ignore */ } finally {
      setSaving(false)
    }
  }

  async function handleExpand(taskId: string) {
    if (expandedTask === taskId) {
      setExpandedTask(null)
      return
    }
    setExpandedTask(taskId)
    setLoadingRuns(taskId)
    try {
      const { runs: r } = await listRuns(agentId, taskId)
      setRuns((prev) => ({ ...prev, [taskId]: r }))
    } catch { /* ignore */ } finally {
      setLoadingRuns(null)
    }
  }

  function formatNextRun(nextRun: string | null): string {
    if (!nextRun) return 'Not scheduled'
    const d = new Date(nextRun)
    const now = new Date()
    const diffMs = d.getTime() - now.getTime()
    if (diffMs < 0) return 'Overdue'
    if (diffMs < 60000) return 'Less than a minute'
    if (diffMs < 3600000) return `${Math.round(diffMs / 60000)}m`
    if (diffMs < 86400000) return `${Math.round(diffMs / 3600000)}h`
    return d.toLocaleString()
  }

  const statusColors: Record<string, string> = {
    completed: 'bg-emerald-500/20 text-emerald-400',
    running: 'bg-blue-500/20 text-blue-400',
    failed: 'bg-red-500/20 text-red-400',
    pending: 'bg-yellow-500/20 text-yellow-400',
  }

  if (loading) return <div className="p-6 text-muted-foreground">Loading...</div>

  return (
    <div className="mx-auto max-w-2xl space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-foreground">Scheduled Tasks</h2>
          <p className="text-xs text-muted-foreground mt-1">
            Agent runs your prompt on a schedule. Results appear below and are sent to any outbound webhooks.
          </p>
        </div>
        <Button size="sm" onClick={() => setShowCreate(!showCreate)}>
          {showCreate ? 'Cancel' : '+ New Schedule'}
        </Button>
      </div>

      {showCreate && (
        <ScheduleForm
          name={name}
          cronExpr={cronExpr}
          prompt={prompt}
          onNameChange={setName}
          onCronChange={setCronExpr}
          onPromptChange={setPrompt}
          onSubmit={handleCreate}
          submitting={creating}
          submitLabel="Create Schedule"
          submittingLabel="Creating..."
        />
      )}

      {schedules.length === 0 ? (
        <div className="py-12 text-center">
          <div className="text-4xl mb-3">&#128337;</div>
          <div className="text-sm text-muted-foreground">
            No scheduled tasks yet. Create one to make your agent run automatically.
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          {schedules.map((sched) => (
            <div key={sched.id} className="rounded-lg border border-border">
              {editingId === sched.id ? (
                /* ── Edit mode ── */
                <div className="p-4">
                  <div className="flex items-center justify-between mb-3">
                    <h4 className="text-sm font-medium text-foreground">Edit Schedule</h4>
                    <button
                      onClick={cancelEditing}
                      className="text-xs text-muted-foreground hover:text-foreground"
                    >
                      Cancel
                    </button>
                  </div>
                  <ScheduleForm
                    name={editName}
                    cronExpr={editCron}
                    prompt={editPrompt}
                    onNameChange={setEditName}
                    onCronChange={setEditCron}
                    onPromptChange={setEditPrompt}
                    onSubmit={handleSaveEdit}
                    submitting={saving}
                    submitLabel="Save Changes"
                    submittingLabel="Saving..."
                    compact
                  />
                </div>
              ) : (
                /* ── View mode ── */
                <>
                  <div className="flex items-center justify-between p-4">
                    <div className="min-w-0 flex-1 cursor-pointer" onClick={() => handleExpand(sched.id)}>
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-foreground">{sched.name || sched.cron_expr}</span>
                        <span className={`inline-block h-2 w-2 rounded-full ${sched.is_active ? 'bg-emerald-500' : 'bg-zinc-500'}`} />
                      </div>
                      <div className="mt-1 flex items-center gap-3 text-xs text-muted-foreground">
                        <code>{sched.cron_expr}</code>
                        <span>&middot;</span>
                        <span>Next: {formatNextRun(sched.next_run)}</span>
                        {sched.last_run && (
                          <>
                            <span>&middot;</span>
                            <span>Last: {new Date(sched.last_run).toLocaleString()}</span>
                          </>
                        )}
                      </div>
                      <div className="mt-2 text-xs text-muted-foreground truncate">
                        Prompt: {sched.prompt.slice(0, 100)}{sched.prompt.length > 100 ? '...' : ''}
                      </div>
                    </div>
                    <div className="flex items-center gap-2 ml-4">
                      <button
                        onClick={() => handleExpand(sched.id)}
                        className="rounded px-2 py-1 text-xs bg-muted text-muted-foreground hover:text-foreground"
                      >
                        {expandedTask === sched.id ? 'Hide Runs' : 'View Runs'}
                      </button>
                      <button
                        onClick={() => startEditing(sched)}
                        className="rounded px-2 py-1 text-xs bg-muted text-muted-foreground hover:text-foreground"
                        title="Edit schedule"
                      >
                        Edit
                      </button>
                      <button
                        onClick={() => handleToggle(sched.id, sched.is_active)}
                        className={`rounded px-2 py-1 text-xs ${
                          sched.is_active ? 'bg-emerald-500/20 text-emerald-400' : 'bg-muted text-muted-foreground'
                        }`}
                      >
                        {sched.is_active ? 'Active' : 'Paused'}
                      </button>
                      <button
                        onClick={() => handleDelete(sched.id)}
                        className="rounded p-1 text-muted-foreground hover:bg-destructive/20 hover:text-destructive"
                      >
                        <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                          <path d="M3 3l8 8M11 3l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                        </svg>
                      </button>
                    </div>
                  </div>
                </>
              )}

              {/* Run history (expandable) */}
              {expandedTask === sched.id && editingId !== sched.id && (
                <div className="border-t border-border bg-muted/30 p-4">
                  <h4 className="text-xs font-medium text-muted-foreground mb-3">Run History</h4>
                  {loadingRuns === sched.id ? (
                    <div className="text-xs text-muted-foreground">Loading runs...</div>
                  ) : !runs[sched.id] || runs[sched.id].length === 0 ? (
                    <div className="text-xs text-muted-foreground">
                      No runs yet. The scheduler checks every 60 seconds. Make sure the backend is running.
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {runs[sched.id].map((run) => (
                        <div key={run.id} className="rounded border border-border bg-background p-3">
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2">
                              <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium uppercase ${
                                statusColors[run.status] || 'bg-muted text-muted-foreground'
                              }`}>
                                {run.status}
                              </span>
                              <span className="text-xs text-muted-foreground">
                                {new Date(run.started_at).toLocaleString()}
                              </span>
                            </div>
                            {run.tokens_used > 0 && (
                              <span className="text-xs text-muted-foreground">
                                {run.tokens_used} tokens
                              </span>
                            )}
                          </div>
                          {run.response && (
                            <div className="mt-2 rounded bg-muted p-2 text-xs text-foreground whitespace-pre-wrap max-h-40 overflow-y-auto">
                              {run.response}
                            </div>
                          )}
                          {run.error && (
                            <div className="mt-2 rounded bg-destructive/10 p-2 text-xs text-destructive">
                              {run.error}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

/* ── Reusable schedule form (used for both create and edit) ── */
function ScheduleForm({
  name, cronExpr, prompt,
  onNameChange, onCronChange, onPromptChange,
  onSubmit, submitting, submitLabel, submittingLabel,
  compact = false,
}: {
  name: string
  cronExpr: string
  prompt: string
  onNameChange: (v: string) => void
  onCronChange: (v: string) => void
  onPromptChange: (v: string) => void
  onSubmit: () => void
  submitting: boolean
  submitLabel: string
  submittingLabel: string
  compact?: boolean
}) {
  return (
    <div className={`space-y-4 ${compact ? '' : 'rounded-lg border border-border p-4'}`}>
      <div className="space-y-2">
        <Label>Name (optional)</Label>
        <Input value={name} onChange={(e) => onNameChange(e.target.value)} placeholder="Morning Report" />
      </div>
      <div className="space-y-2">
        <Label>Schedule</Label>
        <div className="flex flex-wrap gap-1.5 mb-2">
          {CRON_PRESETS.map((p) => (
            <button
              key={p.expr}
              onClick={() => onCronChange(p.expr)}
              className={`rounded px-2 py-1 text-xs transition-colors ${
                cronExpr === p.expr
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-muted text-muted-foreground hover:text-foreground'
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
        <Input
          value={cronExpr}
          onChange={(e) => onCronChange(e.target.value)}
          placeholder="0 9 * * *"
          className="font-mono"
        />
      </div>
      <div className="space-y-2">
        <Label>Prompt (what to send to the agent each time)</Label>
        <textarea
          value={prompt}
          onChange={(e) => onPromptChange(e.target.value)}
          rows={3}
          placeholder="Summarize what happened overnight and give me action items."
          className="flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
        />
      </div>
      <Button onClick={onSubmit} disabled={submitting || !cronExpr.trim() || !prompt.trim()}>
        {submitting ? submittingLabel : submitLabel}
      </Button>
    </div>
  )
}
