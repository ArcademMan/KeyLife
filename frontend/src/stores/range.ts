import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import { api } from '../api'

const STORAGE_KEY = 'keylife.range.v1'

function isoToday(): string {
  return new Date().toISOString().slice(0, 10)
}

function isoDaysAgo(n: number): string {
  const d = new Date()
  d.setDate(d.getDate() - n)
  return d.toISOString().slice(0, 10)
}

function startOfMonth(offset = 0): string {
  const d = new Date()
  d.setDate(1)
  d.setMonth(d.getMonth() + offset)
  return d.toISOString().slice(0, 10)
}

function endOfMonth(offset = 0): string {
  const d = new Date()
  d.setDate(1)
  d.setMonth(d.getMonth() + offset + 1)
  d.setDate(0)
  return d.toISOString().slice(0, 10)
}

function daysBetween(a: string, b: string): number {
  const ms = new Date(b).getTime() - new Date(a).getTime()
  return Math.round(ms / 86_400_000) + 1
}

function shiftIso(iso: string, days: number): string {
  const d = new Date(iso)
  d.setDate(d.getDate() + days)
  return d.toISOString().slice(0, 10)
}

export type PresetId = 'today' | 'yesterday' | '7d' | '30d' | '90d' | '1y'
                     | 'this-month' | 'last-month' | 'all' | 'custom'

const ALL_FALLBACK_DAYS = 365 * 5 - 1

let firstDateCache: string | null = null
let firstDatePromise: Promise<string | null> | null = null

async function resolveFirstDate(): Promise<string | null> {
  if (firstDateCache) return firstDateCache
  if (!firstDatePromise) {
    firstDatePromise = api.summary()
      .then(s => { firstDateCache = s.first_recorded_date; return firstDateCache })
      .catch(() => null)
      .finally(() => { firstDatePromise = null })
  }
  return firstDatePromise
}

export interface PresetDef {
  id: PresetId
  label: string
  resolve: () => { start: string; end: string }
}

export const PRESETS: PresetDef[] = [
  { id: 'today',      label: 'Today',      resolve: () => ({ start: isoToday(),       end: isoToday() }) },
  { id: 'yesterday',  label: 'Yesterday',  resolve: () => ({ start: isoDaysAgo(1),    end: isoDaysAgo(1) }) },
  { id: '7d',         label: 'Last 7d',    resolve: () => ({ start: isoDaysAgo(6),    end: isoToday() }) },
  { id: '30d',        label: 'Last 30d',   resolve: () => ({ start: isoDaysAgo(29),   end: isoToday() }) },
  { id: '90d',        label: 'Last 90d',   resolve: () => ({ start: isoDaysAgo(89),   end: isoToday() }) },
  { id: '1y',         label: 'Last year',  resolve: () => ({ start: isoDaysAgo(364),  end: isoToday() }) },
  { id: 'this-month', label: 'This month', resolve: () => ({ start: startOfMonth(0),  end: isoToday() }) },
  { id: 'last-month', label: 'Last month', resolve: () => ({ start: startOfMonth(-1), end: endOfMonth(-1) }) },
  { id: 'all',        label: 'All time',   resolve: () => ({ start: firstDateCache ?? isoDaysAgo(ALL_FALLBACK_DAYS), end: isoToday() }) },
]

interface PersistedState {
  start: string
  end: string
  preset: PresetId
}

function loadPersisted(): PersistedState | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const p = JSON.parse(raw) as PersistedState
    if (!p.start || !p.end || !p.preset) return null
    return p
  } catch {
    return null
  }
}

export const useRangeStore = defineStore('range', () => {
  const persisted = loadPersisted()
  const start = ref(persisted?.start ?? isoDaysAgo(29))
  const end = ref(persisted?.end ?? isoToday())
  const preset = ref<PresetId>(persisted?.preset ?? '30d')

  const params = computed(() => ({ start: start.value, end: end.value }))
  const dayCount = computed(() => daysBetween(start.value, end.value))

  function applyPreset(id: PresetId) {
    const def = PRESETS.find(p => p.id === id)
    if (!def) return
    const r = def.resolve()
    start.value = r.start
    end.value = r.end
    preset.value = id
    if (id === 'all' && firstDateCache == null) {
      resolveFirstDate().then(fd => {
        if (fd && preset.value === 'all') start.value = fd
      })
    }
  }

  function setRange(s: string, e: string) {
    start.value = s
    end.value = e
    preset.value = 'custom'
  }

  function shift(direction: -1 | 1) {
    const span = dayCount.value
    start.value = shiftIso(start.value, direction * span)
    end.value = shiftIso(end.value, direction * span)
    preset.value = 'custom'
  }

  watch([start, end, preset], () => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        start: start.value, end: end.value, preset: preset.value,
      }))
    } catch { /* quota / disabled */ }
  })

  return { start, end, preset, params, dayCount, applyPreset, setRange, shift }
})
