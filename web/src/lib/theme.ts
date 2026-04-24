const STORAGE_KEY = 'aegis_theme'

export type Theme = 'light' | 'dark' | 'system'

export function getTheme(): Theme {
  return (localStorage.getItem(STORAGE_KEY) as Theme) || 'system'
}

export function applyTheme(theme: Theme) {
  const resolved = theme === 'system'
    ? (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
    : theme
  document.documentElement.classList.toggle('dark', resolved === 'dark')
  localStorage.setItem(STORAGE_KEY, theme)
}

export function toggleTheme() {
  const current = document.documentElement.classList.contains('dark') ? 'dark' : 'light'
  const next = current === 'dark' ? 'light' : 'dark'
  applyTheme(next)
  return next
}
