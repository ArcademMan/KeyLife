<script setup lang="ts">
import { computed } from 'vue'
import type { KeyboardLayout, KeyCount, LayoutKey } from '../../types'
import { useHandmapStore, geometricHand } from '../../stores/handmap'

const props = defineProps<{
  layout: KeyboardLayout | null
  keys: KeyCount[]
}>()

const handmap = useHandmapStore()

interface HandRow { side: 'Left' | 'Right'; count: number; pct: number }

// Per-key hand is taken from the user's handmap overrides if present,
// falling back to a geometric default. Keys assigned to "Both" — or that
// geometrically straddle the midline (the spacebar) — split proportionally
// so the bar reflects two-handed contribution.
const rows = computed<HandRow[]>(() => {
  if (!props.layout) return []
  const byExact = new Map<string, LayoutKey>()
  const byVk = new Map<number, LayoutKey>()
  for (const k of props.layout.keys) {
    if (k.vk == null) continue
    if (k.scancode != null) byExact.set(`${k.vk}:${k.scancode}`, k)
    else if (!byVk.has(k.vk)) byVk.set(k.vk, k)
  }

  const mid = props.layout.width / 2
  let left = 0, right = 0

  for (const k of props.keys) {
    const lk = byExact.get(`${k.vk}:${k.scancode}`) ?? byVk.get(k.vk)
    if (!lk) continue
    const override = handmap.get(k.vk, k.scancode)
    const hand = override ?? geometricHand(lk.x, lk.w, props.layout.width)

    if (hand === 'L') {
      left += k.count
    } else if (hand === 'R') {
      right += k.count
    } else {
      const x0 = lk.x
      const x1 = lk.x + (lk.w ?? 1)
      if (x0 < mid && x1 > mid) {
        const span = x1 - x0
        left  += k.count * ((mid - x0) / span)
        right += k.count * ((x1 - mid) / span)
      } else {
        left  += k.count * 0.5
        right += k.count * 0.5
      }
    }
  }

  const tot = left + right
  if (tot === 0) return []
  return [
    { side: 'Left',  count: Math.round(left),  pct: (left  / tot) * 100 },
    { side: 'Right', count: Math.round(right), pct: (right / tot) * 100 },
  ].filter(r => r.count > 0) as HandRow[]
})

function fmt(n: number): string { return n.toLocaleString() }
</script>

<template>
  <div class="panel panel-pad lg:col-span-1">
    <div class="panel-title mb-3">Left vs right hand</div>
    <div
      v-if="!rows.length"
      class="text-sm text-slate-400 py-8 text-center"
    >
      Layout missing — can't classify.
    </div>
    <template v-else>
      <div class="h-3 w-full rounded-full overflow-hidden flex bg-slate-800 mb-3">
        <div
          v-for="r in rows"
          :key="r.side"
          :style="{
            width: r.pct + '%',
            background: r.side === 'Left' ? '#7c5cff' : '#22d3ee',
          }"
          :title="`${r.side}: ${r.pct.toFixed(1)}%`"
        ></div>
      </div>
      <div class="flex flex-col gap-1.5 text-sm">
        <div
          v-for="r in rows"
          :key="r.side"
          class="flex items-center justify-between gap-3"
        >
          <div class="flex items-center gap-2">
            <span
              class="w-2.5 h-2.5 rounded-sm"
              :style="{ background: r.side === 'Left' ? '#7c5cff' : '#22d3ee' }"
              aria-hidden="true"
            ></span>
            <span class="text-slate-300">{{ r.side }}</span>
          </div>
          <div class="flex items-center gap-3 tabular-nums">
            <span class="text-slate-100">{{ fmt(r.count) }}</span>
            <span class="text-slate-400 text-xs w-12 text-right">
              {{ r.pct.toFixed(1) }}%
            </span>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
