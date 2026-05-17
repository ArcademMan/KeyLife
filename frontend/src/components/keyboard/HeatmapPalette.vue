<script setup lang="ts">
import { PALETTES, type HeatmapPaletteApi } from '../../composables/useHeatmapPalette'

defineProps<{
  palette: HeatmapPaletteApi
  maxCount: number
}>()

function fmt(n: number): string { return n.toLocaleString() }
</script>

<template>
  <div class="flex items-center gap-3 text-xs text-slate-300">
    <label class="flex items-center gap-2">
      <span class="text-slate-400">Palette</span>
      <select
        v-model="palette.paletteId.value"
        class="bg-slate-800 border border-slate-700 rounded px-2 py-1 text-xs text-slate-100"
        aria-label="Heatmap palette"
      >
        <option v-for="p in PALETTES" :key="p.id" :value="p.id">{{ p.label }}</option>
      </select>
    </label>
    <template v-if="palette.paletteId.value === 'custom'">
      <label class="flex items-center gap-1">
        <span class="text-slate-400">cold</span>
        <input
          type="color"
          v-model="palette.customCold.value"
          class="h-6 w-8 rounded bg-transparent border border-slate-700 cursor-pointer"
          aria-label="Cold color"
        />
      </label>
      <label class="flex items-center gap-1">
        <span class="text-slate-400">hot</span>
        <input
          type="color"
          v-model="palette.customHot.value"
          class="h-6 w-8 rounded bg-transparent border border-slate-700 cursor-pointer"
          aria-label="Hot color"
        />
      </label>
    </template>
    <div class="flex items-center gap-2">
      <span class="tabular-nums text-slate-400">0</span>
      <div
        class="h-2 w-40 rounded-full"
        :style="{ background: palette.gradientCss.value }"
        aria-hidden="true"
      ></div>
      <span class="tabular-nums text-slate-300">{{ fmt(maxCount) }}</span>
    </div>
  </div>
</template>
