<script setup lang="ts">
import { computed, ref } from 'vue'
import type { KeyboardLayout, KeyCount } from '../../types'
import { canonicalVk, displayName, VK_TO_NAME } from '../../lib/vk'

const props = defineProps<{
  layout: KeyboardLayout | null
  keys: KeyCount[]
  total: number
}>()

const search = ref('')

const labelByExact = computed(() => {
  const map = new Map<string, string>()
  for (const k of props.layout?.keys ?? []) {
    if (k.vk != null && k.scancode != null) {
      map.set(`${k.vk}:${k.scancode}`, k.label)
    }
  }
  return map
})

const labelByVk = computed(() => {
  const map = new Map<number, string>()
  for (const k of props.layout?.keys ?? []) {
    if (k.vk != null && k.scancode == null && !map.has(k.vk)) {
      map.set(k.vk, k.label)
    }
  }
  return map
})

interface Row {
  vk: number
  scancode: number
  rawName: string
  display: string
  count: number
  pct: number
}

// Merge rows that resolve to the same human-visible label. Windows feeds
// us scancode variants we can't always tell apart in the data — most
// notably the phantom LCtrl injected before AltGr on IT layouts, which
// arrives as VK_RCONTROL with the AltGr scancode, or ghost events that
// share a VK with a different scancode tail. Without this merge each
// physical key can appear two or three times in the table; the heatmap
// already aggregates these under the canonical VK, so collapsing by
// displayName here keeps the two views consistent.
const allRows = computed<Row[]>(() => {
  const merged = new Map<string, Row>()
  for (const k of props.keys) {
    const vk = canonicalVk(k.vk, k.scancode)
    const name = vk !== k.vk ? (VK_TO_NAME[vk] ?? k.name) : k.name
    const display = displayName(vk, k.scancode, name, labelByExact.value, labelByVk.value)
    const existing = merged.get(display)
    if (existing) {
      existing.count += k.count
    } else {
      merged.set(display, {
        vk, scancode: k.scancode, rawName: name, display,
        count: k.count, pct: 0,
      })
    }
  }
  const rows = Array.from(merged.values())
  for (const r of rows) r.pct = props.total > 0 ? (r.count / props.total) * 100 : 0
  rows.sort((a, b) => b.count - a.count)
  return rows
})

const filteredRows = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return allRows.value
  return allRows.value.filter(r =>
    r.display.toLowerCase().includes(q) ||
    r.rawName.toLowerCase().includes(q),
  )
})

function fmt(n: number): string { return n.toLocaleString() }
</script>

<template>
  <div class="panel panel-pad">
    <div class="flex items-baseline justify-between gap-3 mb-3 flex-wrap">
      <div>
        <div class="panel-title">All keys</div>
        <div class="text-xs text-slate-400 mt-0.5 tabular-nums">
          {{ filteredRows.length }} of {{ allRows.length }}
          tracked key{{ allRows.length === 1 ? '' : 's' }}
        </div>
      </div>
      <input
        v-model="search"
        type="search"
        placeholder="Filter by name…"
        aria-label="Filter keys"
        class="bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5
               text-sm text-slate-100 placeholder:text-slate-500
               w-full sm:w-56"
      />
    </div>

    <div v-if="!allRows.length" class="text-sm text-slate-400 py-8 text-center">
      No data yet — keep typing.
    </div>
    <div
      v-else-if="!filteredRows.length"
      class="text-sm text-slate-400 py-8 text-center"
    >
      No keys match "{{ search }}".
    </div>
    <div v-else class="overflow-auto max-h-[480px] -mx-2">
      <table class="w-full text-sm">
        <thead
          class="sticky top-0 bg-slate-900 text-xs uppercase
                 tracking-wider text-slate-400"
        >
          <tr>
            <th class="text-left font-semibold px-3 py-2 w-12">#</th>
            <th class="text-left font-semibold px-3 py-2">Key</th>
            <th class="text-right font-semibold px-3 py-2">Count</th>
            <th class="text-left font-semibold px-3 py-2 w-1/3">Share</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(row, i) in filteredRows"
            :key="row.vk + ':' + row.scancode"
            class="border-t border-slate-800 hover:bg-slate-800/40"
          >
            <td class="px-3 py-1.5 text-slate-500 tabular-nums">{{ i + 1 }}</td>
            <td class="px-3 py-1.5">
              <div class="font-medium text-slate-100">{{ row.display }}</div>
              <div class="text-[10px] text-slate-500 tabular-nums">
                vk {{ row.vk }} · sc {{ row.scancode }}
              </div>
            </td>
            <td class="px-3 py-1.5 text-right tabular-nums text-slate-100">
              {{ fmt(row.count) }}
            </td>
            <td class="px-3 py-1.5">
              <div class="flex items-center gap-2">
                <div class="flex-1 h-1.5 bg-slate-800 rounded-full overflow-hidden">
                  <div class="h-full bg-accent" :style="{ width: row.pct + '%' }"></div>
                </div>
                <span class="text-xs text-slate-400 tabular-nums w-12 text-right">
                  {{ row.pct.toFixed(row.pct < 0.1 ? 2 : 1) }}%
                </span>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
