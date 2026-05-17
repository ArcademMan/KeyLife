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
