import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

export type Hand = 'L' | 'R' | 'B'

const STORAGE_KEY = 'keylife.handmap.v1'

interface Persisted {
  overrides: Record<string, Hand>
}

function makeKey(vk: number, scancode: number | null | undefined): string {
  return scancode != null ? `${vk}:${scancode}` : `${vk}`
}

export const useHandmapStore = defineStore('handmap', () => {
  const overrides = ref<Record<string, Hand>>({})

  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const p = JSON.parse(raw) as Persisted
      if (p?.overrides && typeof p.overrides === 'object') {
        overrides.value = p.overrides
      }
    }
  } catch { /* ignore */ }

  function get(vk: number, scancode?: number | null): Hand | undefined {
    const exact = overrides.value[makeKey(vk, scancode)]
    if (exact) return exact
    if (scancode != null) return overrides.value[makeKey(vk, null)]
    return undefined
  }

  function set(vk: number, scancode: number | null | undefined, hand: Hand) {
    overrides.value = { ...overrides.value, [makeKey(vk, scancode)]: hand }
  }

  function unset(vk: number, scancode?: number | null) {
    const k = makeKey(vk, scancode)
    if (k in overrides.value) {
      const next = { ...overrides.value }
      delete next[k]
      overrides.value = next
    }
  }

  function resetAll() {
    overrides.value = {}
  }

  function setMany(entries: Record<string, Hand>) {
    overrides.value = { ...overrides.value, ...entries }
  }

  watch(overrides, (v) => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ overrides: v } as Persisted))
    } catch { /* ignore */ }
  }, { deep: true })

  return { overrides, get, set, unset, resetAll, setMany }
})

// Geometric default classification (used when no override exists).
export function geometricHand(
  x: number,
  w: number | undefined,
  layoutWidth: number,
): Hand {
  const x0 = x
  const x1 = x + (w ?? 1)
  const mid = layoutWidth / 2
  if (x1 <= mid) return 'L'
  if (x0 >= mid) return 'R'
  return 'B'
}
