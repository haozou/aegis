import { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/stores/auth-store'
import { updateProfile, changePassword } from '@/api/auth'
import { toggleTheme } from '@/lib/theme'

interface Props {
  collapsed?: boolean
  dropdownPosition?: 'above' | 'below'
}

type MenuView = 'main' | 'profile' | 'password'

export function UserMenu({ collapsed = false, dropdownPosition = 'above' }: Props) {
  const { user, updateUser, logout } = useAuthStore()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [view, setView] = useState<MenuView>('main')
  const [displayName, setDisplayName] = useState('')
  const [currentPw, setCurrentPw] = useState('')
  const [newPw, setNewPw] = useState('')
  const [confirmPw, setConfirmPw] = useState('')
  const [saving, setSaving] = useState(false)
  const [pwError, setPwError] = useState('')
  const [pwSuccess, setPwSuccess] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

  // Close on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpen(false)
        setView('main')
      }
    }
    if (open) document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [open])

  if (!user) return null

  const initials = (user.display_name || user.username || user.email)
    .split(' ')
    .map(w => w[0])
    .slice(0, 2)
    .join('')
    .toUpperCase()

  function handleOpen() {
    if (!open) {
      setDisplayName(user!.display_name || '')
      setCurrentPw(''); setNewPw(''); setConfirmPw('')
      setPwError(''); setPwSuccess(false)
      setView('main')
    }
    setOpen(!open)
  }

  async function handleSaveProfile() {
    setSaving(true)
    try {
      const { user: updated } = await updateProfile({ display_name: displayName.trim() || undefined })
      updateUser(updated)
      setView('main')
    } catch { /* ignore */ } finally {
      setSaving(false)
    }
  }

  async function handleChangePassword() {
    setPwError('')
    if (newPw.length < 6) { setPwError('Password must be at least 6 characters'); return }
    if (newPw !== confirmPw) { setPwError('Passwords do not match'); return }

    setSaving(true)
    try {
      await changePassword(currentPw, newPw)
      setPwSuccess(true)
      setTimeout(() => { setView('main'); setPwSuccess(false) }, 1500)
    } catch (e) {
      setPwError(e instanceof Error ? e.message : 'Failed to change password')
    } finally {
      setSaving(false)
    }
  }

  function handleLogout() {
    logout()
    navigate('/login', { replace: true })
  }

  return (
    <div className="relative" ref={menuRef}>
      <button
        onClick={handleOpen}
        className={`flex items-center gap-2 rounded-lg transition-colors hover:bg-sidebar-accent ${
          collapsed ? 'justify-center p-2' : 'w-full px-2 py-2'
        }`}
        title={collapsed ? (user.display_name || user.username) : undefined}
      >
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/20 text-[11px] font-semibold text-primary">
          {initials}
        </div>
        {!collapsed && (
          <div className="flex-1 min-w-0 text-left">
            <div className="truncate text-xs font-medium text-sidebar-foreground">
              {user.display_name || user.username}
            </div>
          </div>
        )}
      </button>

      {/* Dropdown */}
      {open && (
        <div className={`absolute z-50 w-72 rounded-lg border border-border bg-popover shadow-xl ${
          collapsed
            ? 'left-full ml-2 bottom-0'
            : dropdownPosition === 'above'
              ? 'left-0 bottom-full mb-2'
              : 'right-0 top-full mt-2'
        }`}>
          {/* Header — always visible */}
          <div className="p-3 border-b border-border">
            <div className="flex items-center gap-2.5">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/20 text-xs font-semibold text-primary">
                {initials}
              </div>
              <div className="min-w-0">
                <div className="text-sm font-medium text-foreground truncate">{user.display_name || user.username}</div>
                <div className="text-[11px] text-muted-foreground truncate">{user.email}</div>
              </div>
            </div>
          </div>

          {/* Main view */}
          {view === 'main' && (
            <div className="p-1">
              <button onClick={() => setView('profile')}
                className="flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-sm text-foreground hover:bg-muted/50 transition-colors">
                <svg width="14" height="14" viewBox="0 0 16 16" fill="none" className="text-muted-foreground shrink-0">
                  <path d="M8 14a6 6 0 100-12 6 6 0 000 12z" stroke="currentColor" strokeWidth="1.3" />
                  <circle cx="8" cy="6.5" r="2" stroke="currentColor" strokeWidth="1.3" />
                  <path d="M4.5 12.5c0-2 1.6-3 3.5-3s3.5 1 3.5 3" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
                </svg>
                Edit Profile
              </button>
              <button onClick={() => { setCurrentPw(''); setNewPw(''); setConfirmPw(''); setPwError(''); setPwSuccess(false); setView('password') }}
                className="flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-sm text-foreground hover:bg-muted/50 transition-colors">
                <svg width="14" height="14" viewBox="0 0 16 16" fill="none" className="text-muted-foreground shrink-0">
                  <rect x="3" y="7" width="10" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.3" />
                  <path d="M5 7V5a3 3 0 016 0v2" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
                  <circle cx="8" cy="10.5" r="1" fill="currentColor" />
                </svg>
                Change Password
              </button>
              <button onClick={() => { toggleTheme(); setOpen(false) }}
                className="flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-sm text-foreground hover:bg-muted/50 transition-colors">
                <svg width="14" height="14" viewBox="0 0 16 16" fill="none" className="text-muted-foreground shrink-0">
                  <circle cx="8" cy="8" r="4" stroke="currentColor" strokeWidth="1.3" />
                  <path d="M8 1v2M8 13v2M1 8h2M13 8h2M3.05 3.05l1.41 1.41M11.54 11.54l1.41 1.41M3.05 12.95l1.41-1.41M11.54 4.46l1.41-1.41" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
                </svg>
                Toggle Theme
              </button>
              <div className="my-1 border-t border-border" />
              <button onClick={handleLogout}
                className="flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-sm text-destructive hover:bg-destructive/10 transition-colors">
                <svg width="14" height="14" viewBox="0 0 16 16" fill="none" className="shrink-0">
                  <path d="M6 2H4a2 2 0 00-2 2v8a2 2 0 002 2h2M10.5 11.5L14 8l-3.5-3.5M14 8H6" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                Sign Out
              </button>
            </div>
          )}

          {/* Edit Profile view */}
          {view === 'profile' && (
            <div className="p-3 space-y-3">
              <div className="space-y-1.5">
                <label className="text-[11px] font-medium text-muted-foreground">Display Name</label>
                <input
                  value={displayName}
                  onChange={e => setDisplayName(e.target.value)}
                  className="w-full rounded-md border border-input bg-transparent px-2.5 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                  placeholder="Your name"
                  autoFocus
                  onKeyDown={e => { if (e.key === 'Enter') handleSaveProfile(); if (e.key === 'Escape') setView('main') }}
                />
              </div>
              <div className="flex gap-2">
                <button onClick={handleSaveProfile} disabled={saving}
                  className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
                  {saving ? 'Saving...' : 'Save'}
                </button>
                <button onClick={() => setView('main')}
                  className="rounded-md px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground">
                  Cancel
                </button>
              </div>
            </div>
          )}

          {/* Change Password view */}
          {view === 'password' && (
            <div className="p-3 space-y-3">
              {pwSuccess ? (
                <div className="flex items-center gap-2 text-sm text-emerald-400 py-2">
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                    <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="1.3" />
                    <path d="M5.5 8l2 2 3.5-4" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                  Password updated!
                </div>
              ) : (
                <>
                  <div className="space-y-1.5">
                    <label className="text-[11px] font-medium text-muted-foreground">Current Password</label>
                    <input
                      type="password"
                      value={currentPw}
                      onChange={e => setCurrentPw(e.target.value)}
                      className="w-full rounded-md border border-input bg-transparent px-2.5 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                      autoFocus
                    />
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-[11px] font-medium text-muted-foreground">New Password</label>
                    <input
                      type="password"
                      value={newPw}
                      onChange={e => setNewPw(e.target.value)}
                      className="w-full rounded-md border border-input bg-transparent px-2.5 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-[11px] font-medium text-muted-foreground">Confirm New Password</label>
                    <input
                      type="password"
                      value={confirmPw}
                      onChange={e => setConfirmPw(e.target.value)}
                      className="w-full rounded-md border border-input bg-transparent px-2.5 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                      onKeyDown={e => { if (e.key === 'Enter') handleChangePassword() }}
                    />
                  </div>
                  {pwError && (
                    <div className="text-xs text-destructive">{pwError}</div>
                  )}
                  <div className="flex gap-2">
                    <button onClick={handleChangePassword} disabled={saving || !currentPw || !newPw}
                      className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
                      {saving ? 'Updating...' : 'Update Password'}
                    </button>
                    <button onClick={() => setView('main')}
                      className="rounded-md px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground">
                      Cancel
                    </button>
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
