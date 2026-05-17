<script setup lang="ts">
import { computed } from 'vue'
import type { KeyCount } from '../../types'
import { MODIFIER_GROUPS } from '../../lib/vk'

const props = defineProps<{ keys: KeyCount[]; total: number }>()

interface Row { name: string; count: number; pct: number }

const rows = computed<Row[]>(() => MODIFIER_GROUPS.map(g => {
  let count = 0
  for (const k of props.keys) {
    if (g.vks.includes(k.vk)) count += k.count
  }
  return {
    name: g.name,
    count,
    pct: props.total > 0 ? (count / props.total) * 100 : 0,
  }
}).filter(r => r.count > 0))

const share = computed(() => rows.value.reduce((s, r) => s + r.pct, 0))

function fmt(n: number): string { return n.toLocaleString() }
</script>

<template>
  <div class="panel panel-pad lg:col-span-1">
    <div class="flex items-baseline justify-between mb-3">
      <div class="panel-title">Modifiers</div>
      <div class="text-xs text-slate-400 tabular-nums">
        {{ share.toFixed(1) }}% of all presses
      </div>
    </div>
    <div
      v-if="!rows.length"
      class="text-sm text-slate-400 py-8 text-center"
    >
      No modifier presses in range.
    </div>
    <div v-else class="flex flex-col gap-2">
      <div v-for="r in rows" :key="r.name" class="flex items-center gap-3 text-sm">
        <span class="w-12 text-slate-300">{{ r.name }}</span>
        <div class="flex-1 h-2 bg-slate-800 rounded-full overflow-hidden">
          <div class="h-full" :style="{ width: r.pct + '%', background: '#f59e0b' }"></div>
        </div>
        <span class="tabular-nums text-slate-100 w-16 text-right">
          {{ fmt(r.count) }}
        </span>
        <span class="tabular-nums text-slate-400 w-12 text-right text-xs">
          {{ r.pct.toFixed(r.pct < 0.1 ? 2 : 1) }}%
        </span>
      </div>
    </div>
  </div>
</template>
