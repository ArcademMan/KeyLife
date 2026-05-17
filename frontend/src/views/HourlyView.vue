<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { api } from '../api'
import { useRangeStore } from '../stores/range'
import type { HourlyHeatmap } from '../types'
import ChartBox from '../components/ChartBox.vue'
import { isoWeekday } from '../lib/date'
import { AXIS_VALUE, COLORS, TOOLTIP, visualMap } from '../lib/chartTheme'
import { useLivePoll } from '../composables/useLivePoll'

const data = ref<HourlyHeatmap | null>(null)
const loading = ref(true)
const error = ref<string | null>(null)

const range = useRangeStore()
const { params } = storeToRefs(range)

async function load() {
  try {
    loading.value = true
    data.value = await api.hourly(params.value)
    error.value = null
  } catch (e: any) {
    error.value = e?.message ?? 'failed to load'
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(params, load, { deep: true })
useLivePoll(load)

const HOURS = Array.from({ length: 24 }, (_, i) => `${String(i).padStart(2, '0')}:00`)
const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

const dates = computed(() => {
  const set = new Set<string>()
  for (const c of data.value?.cells ?? []) set.add(c.date)
  return Array.from(set).sort()
})

// How many distinct dates fall on each weekday (Mon..Sun) in the loaded
// range, counting *every* day with data — even hours where total=0 are
// still part of the same date set.
const datesPerWeekday = computed<number[]>(() => {
  const counts = new Array(7).fill(0)
  for (const d of dates.value) counts[isoWeekday(d)]++
  return counts
})

const HEATMAP_AXIS = {
  type: 'category' as const,
  axisLine: { lineStyle: { color: COLORS.axisLine } },
  axisLabel: { color: COLORS.axisLabel, fontSize: 11 },
  splitArea: { show: false },
}

const heatmapOption = computed(() => {
  const cells = data.value?.cells ?? []
  const dateIdx = new Map(dates.value.map((d, i) => [d, i]))
  const matrix = cells.map(c => [c.hour, dateIdx.get(c.date) ?? 0, c.total])
  const max = matrix.reduce((m, [, , v]) => Math.max(m, v as number), 0)

  return {
    backgroundColor: 'transparent',
    // No fade-in: the chart re-renders on each poll tick and animation
    // makes the canvas flicker on long ranges (thousands of cells).
    animation: false,
    tooltip: {
      position: 'top',
      ...TOOLTIP,
      formatter: (p: any) => {
        const [h, dIdx, v] = p.value
        return `${dates.value[dIdx]} • ${HOURS[h]}<br><b>${(v as number).toLocaleString()}</b> presses`
      },
    },
    grid: { left: 90, right: 30, top: 50, bottom: 60 },
    xAxis: { ...HEATMAP_AXIS, data: HOURS },
    yAxis: { ...HEATMAP_AXIS, data: dates.value },
    visualMap: visualMap(max),
    series: [{
      type: 'heatmap',
      data: matrix,
      itemStyle: { borderColor: COLORS.heatmapBorder, borderWidth: 0.5 },
      emphasis: { itemStyle: { shadowBlur: 8, shadowColor: COLORS.accent } },
    }],
  }
})

const aggHourOption = computed(() => {
  const totals = new Array(24).fill(0)
  for (const c of data.value?.cells ?? []) totals[c.hour] += c.total
  return {
    backgroundColor: 'transparent',
    grid: { left: 50, right: 20, top: 20, bottom: 30 },
    tooltip: {
      trigger: 'axis', axisPointer: { type: 'shadow' },
      ...TOOLTIP,
      formatter: (p: any) => {
        const it = p[0]
        return `${it.name}<br><b>${(it.value as number).toLocaleString()}</b> presses`
      },
    },
    xAxis: {
      type: 'category', data: HOURS,
      axisLine: { lineStyle: { color: COLORS.axisLine } },
      axisLabel: { color: COLORS.axisLabel, fontSize: 10 },
    },
    yAxis: { type: 'value', ...AXIS_VALUE },
    series: [{
      type: 'bar',
      data: totals,
      itemStyle: { color: COLORS.accent, borderRadius: [4, 4, 0, 0] },
      barWidth: '60%',
    }],
  }
})

// Aggregated by weekday (Mon..Sun). To not bias by uneven # of weekday
// occurrences in the range, we show the *mean per occurrence* of that weekday.
const aggWeekdayOption = computed(() => {
  const totals = new Array(7).fill(0)
  for (const c of data.value?.cells ?? []) {
    totals[isoWeekday(c.date)] += c.total
  }
  const occ = datesPerWeekday.value
  const means = totals.map((t, i) => occ[i] > 0 ? Math.round(t / occ[i]) : 0)
  return {
    backgroundColor: 'transparent',
    grid: { left: 50, right: 20, top: 20, bottom: 30 },
    tooltip: {
      trigger: 'axis', axisPointer: { type: 'shadow' },
      ...TOOLTIP,
      formatter: (p: any) => {
        const it = p[0]
        const i = it.dataIndex as number
        return `${WEEKDAYS[i]}<br>
          mean <b>${means[i].toLocaleString()}</b> presses
          <br><span style="color:#94a3b8">total ${totals[i].toLocaleString()} • ${occ[i]} day${occ[i] === 1 ? '' : 's'}</span>`
      },
    },
    xAxis: {
      type: 'category', data: WEEKDAYS,
      axisLine: { lineStyle: { color: COLORS.axisLine } },
      axisLabel: { color: COLORS.axisLabel, fontSize: 11 },
    },
    yAxis: { type: 'value', ...AXIS_VALUE },
    series: [{
      type: 'bar',
      data: means,
      itemStyle: { color: COLORS.accent, borderRadius: [4, 4, 0, 0] },
      barWidth: '60%',
    }],
  }
})

// Heatmap weekday × hour: mean per occurrence.
const weekdayHourOption = computed(() => {
  const sums: number[][] = Array.from({ length: 7 }, () => new Array(24).fill(0))
  for (const c of data.value?.cells ?? []) {
    sums[isoWeekday(c.date)][c.hour] += c.total
  }
  const occ = datesPerWeekday.value
  const matrix: [number, number, number][] = []
  let max = 0
  for (let wd = 0; wd < 7; wd++) {
    for (let h = 0; h < 24; h++) {
      const mean = occ[wd] > 0 ? sums[wd][h] / occ[wd] : 0
      matrix.push([h, wd, Math.round(mean)])
      if (mean > max) max = mean
    }
  }

  return {
    backgroundColor: 'transparent',
    tooltip: {
      position: 'top',
      ...TOOLTIP,
      formatter: (p: any) => {
        const [h, wd, v] = p.value
        return `${WEEKDAYS[wd]} • ${HOURS[h]}<br>
          mean <b>${(v as number).toLocaleString()}</b> presses
          <br><span style="color:#94a3b8">over ${occ[wd]} day${occ[wd] === 1 ? '' : 's'}</span>`
      },
    },
    grid: { left: 70, right: 30, top: 30, bottom: 60 },
    xAxis: { ...HEATMAP_AXIS, data: HOURS },
    yAxis: { ...HEATMAP_AXIS, data: WEEKDAYS },
    visualMap: visualMap(Math.round(max)),
    series: [{
      type: 'heatmap',
      data: matrix,
      itemStyle: { borderColor: COLORS.heatmapBorder, borderWidth: 0.5 },
      emphasis: { itemStyle: { shadowBlur: 8, shadowColor: COLORS.accent } },
    }],
  }
})

// Click on heatmap cell → drill range to the clicked date.
function onHeatmapClick(p: any) {
  if (!p?.value) return
  const dIdx = (p.value as any[])[1] as number
  const date = dates.value[dIdx]
  if (!date) return
  range.setRange(date, date)
}

const isSingleDay = computed(() => params.value.start === params.value.end)

// Heatmap height grows ~14px per day. Cap at 9000px so we stay under the
// per-browser canvas size limit (~10–16k px) on multi-year ranges; the
// outer scroll container handles overflow above ~70vh.
const heatmapHeight = computed(() => {
  const ideal = dates.value.length * 14 + 130
  return Math.min(Math.max(ideal, 260), 9000) + 'px'
})
</script>

<template>
  <div v-if="error" class="panel panel-pad text-red-300" role="alert">
    {{ error }}
  </div>

  <div v-else class="space-y-6">
    <div class="panel panel-pad">
      <div class="flex items-baseline justify-between mb-3 gap-3 flex-wrap">
        <div>
          <div class="panel-title">When you type — day × hour</div>
          <div class="text-[10px] text-slate-500 mt-0.5">
            click a row to focus on that day
          </div>
        </div>
        <button
          v-if="isSingleDay"
          type="button"
          class="btn text-xs"
          @click="range.applyPreset('30d')"
        >
          ← back to 30d
        </button>
      </div>
      <div class="overflow-auto" :style="{ maxHeight: '70vh' }">
        <ChartBox
          :option="heatmapOption"
          :height="heatmapHeight"
          @chart-click="onHeatmapClick"
        />
      </div>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <div class="panel panel-pad">
        <div class="panel-title mb-3">Aggregated by hour of day</div>
        <ChartBox :option="aggHourOption" height="260px" />
      </div>

      <div class="panel panel-pad">
        <div class="flex items-baseline justify-between mb-3">
          <div class="panel-title">By weekday</div>
          <div class="text-[10px] text-slate-500">mean per occurrence</div>
        </div>
        <ChartBox :option="aggWeekdayOption" height="260px" />
      </div>
    </div>

    <div class="panel panel-pad">
      <div class="flex items-baseline justify-between mb-3">
        <div class="panel-title">Habits — weekday × hour</div>
        <div class="text-[10px] text-slate-500">mean per occurrence</div>
      </div>
      <ChartBox :option="weekdayHourOption" height="320px" />
    </div>

    <div v-if="loading" class="text-xs text-slate-400" role="status">
      loading…
    </div>
  </div>
</template>
