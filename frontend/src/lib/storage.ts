import { ref, watch, type Ref } from 'vue'

// localStorage wrappers that swallow QuotaExceeded / disabled storage and
// JSON parse errors. The persistence is best-effort: losing user prefs is
// strictly less bad than crashing the app.

export function safeLoadJSON<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(key)
    if (!raw) return null
    return JSON.parse(raw) as T
  } catch {
    return null
  }
}

export function safeSaveJSON(key: string, value: unknown): void {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch { /* quota / disabled */ }
}

// Ref that auto-persists to localStorage. `validate` lets callers reject
// malformed payloads (e.g. wrong shape after a schema bump).
export function usePersistedRef<T>(
  key: string,
  defaultValue: T,
  validate?: (v: unknown) => v is T,
): Ref<T> {
  const loaded = safeLoadJSON<unknown>(key)
  const initial = loaded != null && (!validate || validate(loaded))
    ? (loaded as T)
    : defaultValue
  const r = ref(initial) as Ref<T>
  watch(r, (v) => safeSaveJSON(key, v), { deep: true })
  return r
}
