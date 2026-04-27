<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useRouter } from 'vue-router'
import { api } from '../api'
import { useRangeStore } from '../stores/range'
import type { Timeline } from '../types'
import ChartBox from '../components/ChartBox.vue'

const router = useRouter()

const data = ref<Timeline | null>(null)
const loading = ref(true)
const error = ref<string | null>(null)

const range = useRangeStore()
const { params } = storeToRefs(range)

async function load() {
  try {
    loading.value = true
    data.value = await api.timeline(params.value)
    error.value = null
  } catch (e: any) {
    error.value = e?.message ?? 'failed to load'
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(params, load, { deep: true })

function onCalendarClick(p: any) {
  // ECharts calendar heatmap click: value = [date, total]
  const date = Array.isArray(p?.value) ? p.value[0] as string : null
  if (!date) return
  range.setRange(date, date)
  router.push('/hourly')
}

function onLineClick(p: any) {
  const date = (p?.name ?? null) as string | null
  if (!date) return
  range.setRange(date, date)
  router.push('/hourly')
}

const max = computed(() => {
  let m = 0
  for (const d of data.value?.days ?? []) m = Math.max(m, d.total)
  return m
})

const calendarOption = computed(() => {
  const days = data.value?.days ?? []
  const start = data.value?.start ?? params.value.start
  const end = data.value?.end ?? params.value.end
  return {
    backgroundColor: 'transparent',
    tooltip: {
      backgroundColor: '#0f172a',
      borderColor: '#334155',
      textStyle: { color: '#e2e8f0' },
      formatter: (p: any) => `${p.value[0]}<br><b>${p.value[1].toLocaleString()}</b> presses`,
    },
    visualMap: {
      min: 0,
      max: max.value || 1,
      orient: 'horizontal',
      left: 'center',
      bottom: 8,
      inRange: { color: ['#1e293b', '#3b3170', '#5b46c4', '#7c5cff', '#b39dff'] },
      textStyle: { color: '#cbd5e1' },
    },
    calendar: {
      top: 30,
      left: 50,
      right: 30,
      bottom: 60,
      cellSize: ['auto', 22],
      range: [start, end],
      itemStyle: { color: '#0f172a', borderColor: '#020617', borderWidth: 2 },
      yearLabel: { color: '#cbd5e1' },
      monthLabel: { color: '#cbd5e1', nameMap: 'EN' },
      dayLabel: { color: '#94a3b8', firstDay: 1 },
      splitLine: { show: false },
    },
    series: [{
      type: 'heatmap',
      coordinateSystem: 'calendar',
      data: days.map(d => [d.date, d.total]),
    }],
  }
})

const lineOption = computed(() => {
  const days = data.value?.days ?? []
  return {
    backgroundColor: 'transparent',
    grid: { left: 50, right: 20, top: 20, bottom: 30 },
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#0f172a',
      borderColor: '#334155',
      textStyle: { color: '#e2e8f0' },
    },
    xAxis: {
      type: 'category',
      data: days.map(d => d.date),
      axisLine: { lineStyle: { color: '#334155' } },
      axisLabel: { color: '#94a3b8' },
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: '#1e293b' } },
      axisLabel: { color: '#94a3b8' },
    },
    series: [{
      type: 'line',
      smooth: true,
      symbol: 'circle',
      symbolSize: 4,
      lineStyle: { width: 2, color: '#7c5cff' },
      itemStyle: { color: '#7c5cff' },
      areaStyle: { color: 'rgba(124,92,255,0.12)' },
      data: days.map(d => d.total),
    }],
  }
})
</script>

<template>
  <div v-if="error" class="panel panel-pad text-red-300">{{ error }}</div>

  <div v-else class="space-y-6">
    <div class="panel panel-pad">
      <div class="flex items-baseline justify-between mb-3">
        <div>
          <div class="panel-title">Calendar heatmap</div>
          <div class="text-[10px] text-slate-500 mt-0.5">
            click a day to drill down
          </div>
        </div>
        <div class="text-xs text-slate-400 tabular-nums">
          peak {{ max.toLocaleString() }} / day
        </div>
      </div>
      <ChartBox :option="calendarOption" height="280px" @chart-click="onCalendarClick" />
    </div>

    <div class="panel panel-pad">
      <div class="panel-title mb-3">Daily trend</div>
      <ChartBox :option="lineOption" height="320px" @chart-click="onLineClick" />
    </div>

    <div v-if="loading" class="text-xs text-slate-400" role="status">
      loading…
    </div>
  </div>
</template>
