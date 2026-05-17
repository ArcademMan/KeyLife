// Local-calendar date helpers. The backend keys daily counters on
// `date.today()` in the host's local time, so the frontend must match —
// using UTC (toISOString) would skew by a day during the offset window
// and hide today's presses entirely.

export function isoLocal(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

export function parseIsoLocal(iso: string): Date {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(y, m - 1, d)
}

export function isoToday(): string {
  return isoLocal(new Date())
}

export function isoDaysAgo(n: number): string {
  const d = new Date()
  d.setDate(d.getDate() - n)
  return isoLocal(d)
}

export function startOfMonth(offset = 0): string {
  const d = new Date()
  d.setDate(1)
  d.setMonth(d.getMonth() + offset)
  return isoLocal(d)
}

export function endOfMonth(offset = 0): string {
  const d = new Date()
  d.setDate(1)
  d.setMonth(d.getMonth() + offset + 1)
  d.setDate(0)
  return isoLocal(d)
}

export function daysBetween(a: string, b: string): number {
  const ms = parseIsoLocal(b).getTime() - parseIsoLocal(a).getTime()
  return Math.round(ms / 86_400_000) + 1
}

export function shiftIso(iso: string, days: number): string {
  const d = parseIsoLocal(iso)
  d.setDate(d.getDate() + days)
  return isoLocal(d)
}

// 0 = Monday … 6 = Sunday.
export function isoWeekday(iso: string): number {
  return (parseIsoLocal(iso).getDay() + 6) % 7
}

// "YYYY-MM-DD" → "DD/MM/YYYY"
export function fmtIsoDdMmYyyy(iso: string): string {
  const [y, m, d] = iso.split('-')
  return `${d}/${m}/${y}`
}

// "Just now" / "3 min ago" / "2 h ago" / "yesterday" / "3 d ago" / "DD/MM/YYYY"
// for older. Input is an ISO 8601 UTC timestamp. Returns a localized-ish
// English string; we don't have a real i18n layer.
export function relativeTimeAgo(iso: string | null | undefined): string {
  if (!iso) return '—'
  const then = Date.parse(iso)
  if (Number.isNaN(then)) return '—'
  const diffSec = Math.max(0, (Date.now() - then) / 1000)
  if (diffSec < 45) return 'just now'
  if (diffSec < 60 * 2) return '1 min ago'
  if (diffSec < 60 * 60) return `${Math.round(diffSec / 60)} min ago`
  if (diffSec < 60 * 60 * 2) return '1 h ago'
  if (diffSec < 60 * 60 * 24) return `${Math.round(diffSec / 3600)} h ago`
  if (diffSec < 60 * 60 * 24 * 2) return 'yesterday'
  if (diffSec < 60 * 60 * 24 * 7) return `${Math.round(diffSec / 86400)} d ago`
  const d = new Date(then)
  return `${String(d.getDate()).padStart(2, '0')}/${String(d.getMonth() + 1).padStart(2, '0')}/${d.getFullYear()}`
}

// "1.2 MB" / "456 KB" / "789 B". Decimal units, not binary.
export function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`
  if (n < 1024 * 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(1)} MB`
  return `${(n / (1024 * 1024 * 1024)).toFixed(2)} GB`
}
