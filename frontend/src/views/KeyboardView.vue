<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { api } from '../api'
import { useRangeStore } from '../stores/range'
import type { KeyboardHeatmap, KeyboardLayout, LayoutKey } from '../types'
import KeyboardGrid from '../components/KeyboardGrid.vue'
import HeatmapPalette from '../components/keyboard/HeatmapPalette.vue'
import KeyCategoryChart from '../components/keyboard/KeyCategoryChart.vue'
import ModifierBreakdown from '../components/keyboard/ModifierBreakdown.vue'
import HandBreakdown from '../components/keyboard/HandBreakdown.vue'
import AllKeysTable from '../components/keyboard/AllKeysTable.vue'
import { canonicalVk } from '../lib/vk'
import { useHeatmapPalette } from '../composables/useHeatmapPalette'
import { useLivePoll } from '../composables/useLivePoll'

const layout = ref<KeyboardLayout | null>(null)
const data = ref<KeyboardHeatmap | null>(null)
const error = ref<string | null>(null)
const loading = ref(true)

const range = useRangeStore()
const { params } = storeToRefs(range)

const palette = useHeatmapPalette()

async function load() {
  try {
    loading.value = true
    const [l, h] = await Promise.all([
      layout.value ? Promise.resolve(layout.value) : api.layout(),
      api.keyboard(params.value),
    ])
    layout.value = l
    data.value = h
    error.value = null
  } catch (e: any) {
    error.value = e?.message ?? 'failed to load'
  } finally {
    loading.value = false
  }
}

async function reloadHeatmap(): Promise<void> {
  try {
    data.value = await api.keyboard(params.value)
    error.value = null
  } catch (e: any) {
    error.value = e?.message ?? 'failed to load'
  }
}

onMounted(load)
watch(params, load, { deep: true })
useLivePoll(reloadHeatmap)

interface Tally { exact: Map<string, number>; perVk: Map<number, number> }

const tallies = computed<Tally>(() => {
  const exact = new Map<string, number>()
  const perVk = new Map<number, number>()
  for (const k of data.value?.keys ?? []) {
    const vk = canonicalVk(k.vk, k.scancode)
    exact.set(`${vk}:${k.scancode}`, (exact.get(`${vk}:${k.scancode}`) ?? 0) + k.count)
    perVk.set(vk, (perVk.get(vk) ?? 0) + k.count)
  }
  return { exact, perVk }
})

function countFor(k: LayoutKey): number {
  if (k.vk == null) return 0
  if (k.scancode != null) return tallies.value.exact.get(`${k.vk}:${k.scancode}`) ?? 0
  return tallies.value.perVk.get(k.vk) ?? 0
}

const maxCount = computed(() => {
  let m = 0
  for (const k of layout.value?.keys ?? []) m = Math.max(m, countFor(k))
  return m
})

const totalPresses = computed(() => {
  let s = 0
  for (const k of data.value?.keys ?? []) s += k.count
  return s
})

function fmt(n: number) { return n.toLocaleString() }
</script>

<template>
  <div v-if="error" class="panel panel-pad text-red-300">{{ error }}</div>

  <div v-else class="space-y-6">
    <div class="panel panel-pad flex flex-wrap gap-6 items-center justify-between">
      <div>
        <div class="panel-title">Total presses in range</div>
        <div class="mt-1 text-2xl font-bold tabular-nums">{{ fmt(totalPresses) }}</div>
        <div class="text-xs text-slate-400 tabular-nums">{{ params.start }} → {{ params.end }}</div>
      </div>
      <HeatmapPalette :palette="palette" :max-count="maxCount" />
    </div>

    <div class="panel p-6 overflow-auto">
      <KeyboardGrid v-if="layout" :layout="layout">
        <template #cell="{ keyDef, style }">
          <div
            class="absolute rounded-md border border-slate-700/50 flex flex-col
                   items-center justify-center text-center select-none transition-colors"
            :style="{
              ...style,
              background: palette.bgFor(countFor(keyDef), maxCount),
              color: palette.textColorFor(countFor(keyDef), maxCount),
            }"
            :title="keyDef.label + (keyDef.vk != null ? ` • ${fmt(countFor(keyDef))}` : ' • not tracked')"
          >
            <div class="text-[11px] font-medium leading-none">{{ keyDef.label }}</div>
            <div
              v-if="keyDef.vk != null && countFor(keyDef) > 0"
              class="text-[9px] opacity-80 mt-0.5 tabular-nums leading-none"
            >
              {{ fmt(countFor(keyDef)) }}
            </div>
          </div>
        </template>
      </KeyboardGrid>
    </div>

    <div
      v-if="totalPresses > 0"
      class="grid grid-cols-1 lg:grid-cols-3 gap-6"
    >
      <KeyCategoryChart :keys="data?.keys ?? []" />
      <ModifierBreakdown :keys="data?.keys ?? []" :total="totalPresses" />
      <HandBreakdown :layout="layout" :keys="data?.keys ?? []" />
    </div>

    <AllKeysTable :layout="layout" :keys="data?.keys ?? []" :total="totalPresses" />

    <div v-if="loading" class="text-xs text-slate-400" role="status">
      loading…
    </div>
  </div>
</template>
