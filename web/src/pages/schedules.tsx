import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { listAgents } from '@/api/agents'
import {
  listSchedules,
  createSchedule,
  deleteSchedule,
  toggleSchedule,
  updateSchedule,
  listRuns,
  type Schedule,
  type TaskRun,
} from '@/api/schedules'
import type { Agent } from '@/types'

type ScheduleRow = Schedule & { _agentName: string }

const CRON_PRESETS = [
  { label: 'Every minute', expr: '* * * * *' },
  { label: 'Every 5 min', expr: '*/5 * * * *' },
  { label: 'Every hour', expr: '0 * * * *' },
  { label: 'Daily 9am', expr: '0 9 * * *' },
  { label: 'Daily midnight', expr: '0 0 * * *' },
  { label: 'Weekdays 9am', expr: '0 9 * * 1-5' },
  { label: 'Weekly Mon 9am', expr: '0 9 * * 1' },
]

const statusColors: Record<string, string> = {
  completed: 'bg-emerald-500/20 text-emerald-400',
  running: 'bg-blue-500/20 text-blue-400',
  failed: 'bg-red-500/20 text-red-400',
  pending: 'bg-yellow-500/20 text-yellow-400',
}

function formatNextRun(nextRun: string | null): string {
  if (!nextRun) return 'Not scheduled'
  const d = new Date(nextRun)
  const diffMs = d.getTime() - Date.now()
  if (diffMs < 0) return 'Overdue'
  if (diffMs < 60000) return '<1 min'
  if (diffMs < 3600000) return `${Math.round(diffMs / 60000)}m`
  if (diffMs < 86400000) return `${Math.round(diffMs / 3600000)}h`
  return d.toLocaleString()
}

interface ScheduleFormProps {
  name: string; cronExpr: string; prompt: string
  onNameChange: (v: string) => void
  onCronChange: (v: string) => void
  onPromptChange: (v: string) => void
  onSubmit: () => void
  submitting: boolean; submitLabel: string; submittingLabel: string
  compact?: boolean
}

function ScheduleForm({ name, cronExpr, prompt, onNameChange, onCronChange, onPromptChange,
  onSubmit, submitting, submitLabel, submittingLabel, compact = false }: ScheduleFormProps) {
  return (
    <div className={`space-y-4 ${compact ? '' : ''}`}>
      <div className="space-y-1.5">
        <Label>Name (optional)</Label>
        <Input value={name} onChange={e => onNameChange(e.target.value)} placeholder="Morning Report" />
      </div>
      <div className="space-y-1.5">
        <Label>Schedule</Label>
        <div className="flex flex-wrap gap-1.5 mb-2">
          {CRON_PRESETS.map(p => (
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
        <Input value={cronExpr} onChange={e => onCronChange(e.target.value)} placeholder="0 9 * * *" className="font-mono" />
      </div>
      <div className="space-y-1.5">
        <Label>Prompt</Label>
        <textarea
          value={prompt}
          onChange={e => onPromptChange(e.target.value)}
          rows={3}
          placeholder="Summarize what happened overnight and give me action items."
          className="flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
        />
      </div>
      <Button onClick={onSubmit} disabled={submitting || !cronExpr.trim() || !prompt.trim()} size="sm">
        {submitting ? submittingLabel : submitLabel}
      </Button>
    </div>
  )
}

export function SchedulesPage() {
  const navigate = useNavigate()
  const [agents, setAgents] = useState<Agent[]>([])
  const [schedules, setSchedules] = useState<ScheduleRow[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [selectedAgentId, setSelectedAgentId] = useState('')
  const [name, setName] = useState('')
  const [cronExpr, setCronExpr] = useState('0 9 * * *')
  const [prompt, setPrompt] = useState('')
  const [creating, setCreating] = useState(false)
  const [expandedTask, setExpandedTask] = useState<string | null>(null)
  const [runs, setRuns] = useState<Record<string, TaskRun[]>>({})
  const [loadingRuns, setLoadingRuns] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editName, setEditName] = useState('')
  const [editCron, setEditCron] = useState('')
  const [editPrompt, setEditPrompt] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    listAgents().then(({ agents: list }) => {
      setAgents(list)
      if (list[0]) setSelectedAgentId(list[0].id)
      Promise.allSettled(list.map(a => listSchedules(a.id))).then(results => {
        const all: ScheduleRow[] = []
        results.forEach((r, i) => {
          if (r.status === 'fulfilled') {
            r.value.schedules.forEach(s => all.push({ ...s, _agentName: list[i].name }))
          }
        })
        setSchedules(all)
        setLoading(false)
      })
    }).catch(() => setLoading(false))
  }, [])

  async function handleCreate() {
    if (!selectedAgentId || !cronExpr.trim() || !prompt.trim()) return
    const agentName = agents.find(a => a.id === selectedAgentId)?.name ?? ''
    setCreating(true)
    try {
      const { schedule } = await createSchedule(selectedAgentId, {
        name: name.trim(), cron_expr: cronExpr.trim(), prompt: prompt.trim(),
      })
      setSchedules(prev => [{ ...schedule, _agentName: agentName }, ...prev])
      setName(''); setPrompt(''); setCronExpr('0 9 * * *'); setShowCreate(false)
    } catch { /* ignore */ } finally {
      setCreating(false)
    }
  }

  async function handleDelete(sched: ScheduleRow) {
    if (!confirm('Delete this schedule?')) return
    try {
      await deleteSchedule(sched.agent_id, sched.id)
      setSchedules(prev => prev.filter(s => s.id !== sched.id))
      if (editingId === sched.id) setEditingId(null)
    } catch { /* ignore */ }
  }

  async function handleToggle(sched: ScheduleRow) {
    try {
      const { schedule } = await toggleSchedule(sched.agent_id, sched.id, !sched.is_active)
      setSchedules(prev => prev.map(s => s.id === sched.id ? { ...schedule, _agentName: sched._agentName } : s))
    } catch { /* ignore */ }
  }

  function startEditing(sched: ScheduleRow) {
    setEditingId(sched.id); setEditName(sched.name); setEditCron(sched.cron_expr); setEditPrompt(sched.prompt)
  }

  async function handleSaveEdit() {
    if (!editingId) return
    const sched = schedules.find(s => s.id === editingId)
    if (!sched) return
    setSaving(true)
    try {
      const { schedule } = await updateSchedule(sched.agent_id, editingId, {
        name: editName.trim(), cron_expr: editCron.trim(), prompt: editPrompt.trim(),
      })
      setSchedules(prev => prev.map(s => s.id === editingId ? { ...schedule, _agentName: sched._agentName } : s))
      setEditingId(null)
    } catch { /* ignore */ } finally {
      setSaving(false)
    }
  }

  async function handleExpand(taskId: string) {
    if (expandedTask === taskId) { setExpandedTask(null); return }
    setExpandedTask(taskId)
    const sched = schedules.find(s => s.id === taskId)
    if (!sched) return
    setLoadingRuns(taskId)
    try {
      const { runs: r } = await listRuns(sched.agent_id, taskId)
      setRuns(prev => ({ ...prev, [taskId]: r }))
    } catch { /* ignore */ } finally {
      setLoadingRuns(null)
    }
  }

  return (
    <div className="min-h-svh bg-background">
      {/* Header */}
      <header className="sticky top-0 z-10 border-b border-border bg-card">
        <div className="mx-auto flex max-w-3xl items-center gap-3 px-4 py-3">
          <button
            onClick={() => navigate(-1)}
            className="flex items-center gap-1.5 rounded-lg p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M10 12L6 8l4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
          <div className="flex items-center gap-2 flex-1 min-w-0">
            <span className="text-xl">🕐</span>
            <h1 className="text-base font-semibold text-foreground">Schedules</h1>
            <span className="text-xs text-muted-foreground hidden sm:block">— all agents</span>
          </div>
          <Button size="sm" onClick={() => setShowCreate(v => !v)}>
            {showCreate ? 'Cancel' : '+ New Schedule'}
          </Button>
        </div>
      </header>

      <div className="mx-auto max-w-3xl px-4 py-6 space-y-4">
        {/* Create form */}
        {showCreate && (
          <div className="rounded-lg border border-border bg-card p-5 space-y-4">
            <h3 className="text-sm font-semibold text-foreground">New Scheduled Task</h3>
            <div className="space-y-1.5">
              <Label>Agent</Label>
              <select
                value={selectedAgentId}
                onChange={e => setSelectedAgentId(e.target.value)}
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
              >
                {agents.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
              </select>
            </div>
            <ScheduleForm
              name={name} cronExpr={cronExpr} prompt={prompt}
              onNameChange={setName} onCronChange={setCronExpr} onPromptChange={setPrompt}
              onSubmit={handleCreate} submitting={creating}
              submitLabel="Create Schedule" submittingLabel="Creating…"
            />
          </div>
        )}

        {/* List */}
        {loading ? (
          <div className="py-16 text-center text-sm text-muted-foreground">Loading…</div>
        ) : schedules.length === 0 && !showCreate ? (
          <div className="py-16 text-center">
            <div className="text-5xl mb-4">🕐</div>
            <p className="text-sm font-medium text-foreground">No scheduled tasks yet</p>
            <p className="mt-1 text-xs text-muted-foreground">Create one to make your agents run automatically</p>
          </div>
        ) : (
          <div className="space-y-3">
            {schedules.map(sched => (
              <div key={sched.id} className="rounded-lg border border-border bg-card">
                {editingId === sched.id ? (
                  <div className="p-4">
                    <div className="flex items-center justify-between mb-3">
                      <h4 className="text-sm font-medium text-foreground">Edit Schedule</h4>
                      <button onClick={() => setEditingId(null)} className="text-xs text-muted-foreground hover:text-foreground">Cancel</button>
                    </div>
                    <ScheduleForm
                      name={editName} cronExpr={editCron} prompt={editPrompt}
                      onNameChange={setEditName} onCronChange={setEditCron} onPromptChange={setEditPrompt}
                      onSubmit={handleSaveEdit} submitting={saving}
                      submitLabel="Save Changes" submittingLabel="Saving…"
                      compact
                    />
                  </div>
                ) : (
                  <>
                    <div className="flex items-start justify-between p-4">
                      <div className="min-w-0 flex-1 cursor-pointer" onClick={() => handleExpand(sched.id)}>
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-sm font-medium text-foreground">{sched.name || sched.cron_expr}</span>
                          <span className={`inline-block h-2 w-2 rounded-full shrink-0 ${sched.is_active ? 'bg-emerald-500' : 'bg-zinc-500'}`} />
                          <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-medium text-primary shrink-0">
                            {sched._agentName}
                          </span>
                        </div>
                        <div className="mt-1 flex items-center gap-2 flex-wrap text-xs text-muted-foreground">
                          <code>{sched.cron_expr}</code>
                          <span>&middot;</span>
                          <span>Next: {formatNextRun(sched.next_run)}</span>
                          {sched.last_run && (
                            <><span>&middot;</span><span>Last: {new Date(sched.last_run).toLocaleString()}</span></>
                          )}
                        </div>
                        <div className="mt-1.5 text-xs text-muted-foreground truncate">
                          {sched.prompt.slice(0, 120)}{sched.prompt.length > 120 ? '…' : ''}
                        </div>
                      </div>
                      <div className="flex items-center gap-1.5 ml-4 shrink-0">
                        <button
                          onClick={() => handleExpand(sched.id)}
                          className="rounded px-2 py-1 text-xs bg-muted text-muted-foreground hover:text-foreground"
                        >
                          {expandedTask === sched.id ? 'Hide' : 'Runs'}
                        </button>
                        <button
                          onClick={() => startEditing(sched)}
                          className="rounded px-2 py-1 text-xs bg-muted text-muted-foreground hover:text-foreground"
                        >
                          Edit
                        </button>
                        <button
                          onClick={() => handleToggle(sched)}
                          className={`rounded px-2 py-1 text-xs ${
                            sched.is_active ? 'bg-emerald-500/20 text-emerald-400' : 'bg-muted text-muted-foreground'
                          }`}
                        >
                          {sched.is_active ? 'Active' : 'Paused'}
                        </button>
                        <button
                          onClick={() => handleDelete(sched)}
                          className="rounded p-1 text-muted-foreground hover:bg-destructive/20 hover:text-destructive"
                        >
                          <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
                            <path d="M3 3l8 8M11 3l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                          </svg>
                        </button>
                      </div>
                    </div>
                    {/* Run history */}
                    {expandedTask === sched.id && (
                      <div className="border-t border-border bg-muted/30 p-4">
                        <h4 className="text-xs font-medium text-muted-foreground mb-3">Run History</h4>
                        {loadingRuns === sched.id ? (
                          <div className="text-xs text-muted-foreground">Loading…</div>
                        ) : !runs[sched.id] || runs[sched.id].length === 0 ? (
                          <div className="text-xs text-muted-foreground">No runs yet.</div>
                        ) : (
                          <div className="space-y-2">
                            {runs[sched.id].map(run => (
                              <div key={run.id} className="rounded border border-border bg-background p-3">
                                <div className="flex items-center justify-between">
                                  <div className="flex items-center gap-2">
                                    <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium uppercase ${statusColors[run.status] ?? 'bg-muted text-muted-foreground'}`}>
                                      {run.status}
                                    </span>
                                    <span className="text-xs text-muted-foreground">
                                      {new Date(run.started_at).toLocaleString()}
                                    </span>
                                  </div>
                                  {run.tokens_used > 0 && (
                                    <span className="text-xs text-muted-foreground">{run.tokens_used} tokens</span>
                                  )}
                                </div>
                                {run.response && (
                                  <div className="mt-2 rounded bg-muted p-2 text-xs text-foreground whitespace-pre-wrap max-h-40 overflow-y-auto">
                                    {run.response}
                                  </div>
                                )}
                                {run.error && (
                                  <div className="mt-2 rounded bg-destructive/10 p-2 text-xs text-destructive">{run.error}</div>
                                )}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
