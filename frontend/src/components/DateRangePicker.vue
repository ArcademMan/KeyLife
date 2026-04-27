<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { storeToRefs } from 'pinia'
import { useRangeStore, PRESETS, type PresetId } from '../stores/range'

const range = useRangeStore()
const { start, end, preset, dayCount } = storeToRefs(range)

const open = ref(false)
const root = ref<HTMLDivElement | null>(null)

const QUICK: PresetId[] = ['7d', '30d', '90d', '1y', 'all']
const quickPresets = computed(() => PRESETS.filter(p => QUICK.includes(p.id)))

function fmtIso(iso: string): string {
  const [y, m, d] = iso.split('-')
  return `${d}/${m}/${y}`
}

const triggerLabel = computed(() => {
  const def = PRESETS.find(p => p.id === preset.value)
  if (def && preset.value !== 'custom') return def.label
  return `${fmtIso(start.value)} → ${fmtIso(end.value)}`
})

function onDocClick(e: MouseEvent) {
  if (!root.value) return
  if (!root.value.contains(e.target as Node)) open.value = false
}

function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') open.value = false
}

onMounted(() => {
  document.addEventListener('mousedown', onDocClick)
  document.addEventListener('keydown', onKey)
})
onBeforeUnmount(() => {
  document.removeEventListener('mousedown', onDocClick)
  document.removeEventListener('keydown', onKey)
})

function pickPreset(id: PresetId) {
  range.applyPreset(id)
}
</script>

<template>
  <div ref="root" class="flex items-center gap-2">
    <!-- Segmented quick presets -->
    <div
      class="hidden md:flex items-center gap-0.5 bg-slate-900 border border-slate-700
             rounded-lg p-0.5"
      role="group"
      aria-label="Quick date range"
    >
      <button
        v-for="p in quickPresets"
        :key="p.id"
        type="button"
        class="px-2.5 py-1 rounded-md text-xs font-medium transition"
        :class="preset === p.id
          ? 'bg-accent text-white shadow-sm'
          : 'text-slate-300 hover:text-white hover:bg-slate-800'"
        :aria-pressed="preset === p.id"
        @click="pickPreset(p.id)"
      >
        {{ p.id === 'all' ? 'All' : p.label.replace('Last ', '') }}
      </button>
    </div>

    <!-- Prev / Next period -->
    <div class="flex items-center gap-0.5">
      <button
        type="button"
        class="btn px-2 py-1.5"
        aria-label="Previous period"
        @click="range.shift(-1)"
      >
        <span aria-hidden="true">‹</span>
      </button>
      <button
        type="button"
        class="btn px-2 py-1.5"
        aria-label="Next period"
        @click="range.shift(1)"
      >
        <span aria-hidden="true">›</span>
      </button>
    </div>

    <!-- Trigger / popover -->
    <div class="relative">
      <button
        type="button"
        class="btn flex items-center gap-2 min-w-[200px] justify-between"
        :aria-expanded="open"
        aria-haspopup="dialog"
        @click="open = !open"
      >
        <span class="tabular-nums text-slate-100">{{ triggerLabel }}</span>
        <span class="text-[10px] text-slate-400 tabular-nums">
          {{ dayCount }}d
        </span>
      </button>

      <div
        v-if="open"
        class="absolute right-0 mt-2 w-[420px] bg-slate-900 border border-slate-700
               rounded-xl p-4 z-20 shadow-2xl"
        role="dialog"
        aria-label="Choose date range"
      >
        <div class="flex gap-4">
          <!-- Preset list -->
          <div class="w-40 flex flex-col gap-0.5">
            <div class="panel-title mb-1 text-[10px]">Presets</div>
            <button
              v-for="p in PRESETS"
              :key="p.id"
              type="button"
              class="text-left px-2 py-1.5 rounded-md text-sm transition"
              :class="preset === p.id
                ? 'bg-accent text-white'
                : 'text-slate-300 hover:bg-slate-800'"
              :aria-pressed="preset === p.id"
              @click="pickPreset(p.id)"
            >
              {{ p.label }}
            </button>
          </div>

          <!-- Custom inputs -->
          <div class="flex-1 flex flex-col gap-3">
            <div class="panel-title text-[10px]">Custom</div>
            <label class="flex flex-col gap-1 text-xs text-slate-400">
              <span>From</span>
              <input
                type="date"
                v-model="start"
                @change="preset = 'custom'"
                class="bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5
                       text-slate-100 text-sm tabular-nums"
              />
            </label>
            <label class="flex flex-col gap-1 text-xs text-slate-400">
              <span>To</span>
              <input
                type="date"
                v-model="end"
                @change="preset = 'custom'"
                class="bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5
                       text-slate-100 text-sm tabular-nums"
              />
            </label>
            <div class="text-xs text-slate-400 mt-auto tabular-nums">
              {{ dayCount }} day{{ dayCount === 1 ? '' : 's' }} selected
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
