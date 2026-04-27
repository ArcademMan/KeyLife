<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, computed, watch } from 'vue'
import { api } from '../api'
import type { Summary, Timeline, TopKeys } from '../types'
import StatCard from '../components/StatCard.vue'
import ChartBox from '../components/ChartBox.vue'

const summary = ref<Summary | null>(null)
const timeline = ref<Timeline | null>(null)
const top = ref<TopKeys | null>(null)
const loading = ref(true)
const refreshing = ref(false)
const error = ref<string | null>(null)
const lastSessionTotal = ref<number | null>(null)
const liveTick = ref(false)

async function load() {
  refreshing.value = true
  try {
    const [s, t, k] = await Promise.all([
      api.summary(),
      api.timeline({}),
      api.top({ limit: 10 }),
    ])
    if (
      lastSessionTotal.value != null &&
      s.session_total > lastSessionTotal.value
    ) {
      liveTick.value = true
      window.setTimeout(() => { liveTick.value = false }, 1500)
    }
    lastSessionTotal.value = s.session_total
    summary.value = s
    timeline.value = t
    top.value = k
    error.value = null
  } catch (e: any) {
    error.value = e?.message ?? 'failed to load'
  } finally {
    loading.value = false
    refreshing.value = false
  }
}

let timer: number | undefined
onMounted(() => { load() })

watch(
  () => summary.value?.flush_interval_seconds,
  (sec) => {
    if (timer) clearInterval(timer)
    const ms = Math.max((sec ?? 5) * 1000, 2000)
    timer = window.setInterval(load, ms)
  },
)

onBeforeUnmount(() => { if (timer) clearInterval(timer) })

const sparkOption = computed(() => {
  const days = timeline.value?.days ?? []
  return {
    backgroundColor: 'transparent',
    grid: { left: 0, right: 0, top: 8, bottom: 0 },
    xAxis: { type: 'category', show: false, data: days.map(d => d.date) },
    yAxis: { type: 'value', show: false },
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#0f172a',
      borderColor: '#334155',
      textStyle: { color: '#e2e8f0', fontFamily: 'ui-monospace, monospace' },
    },
    series: [{
      type: 'line',
      smooth: true,
      symbol: 'none',
      lineStyle: { width: 2, color: '#7c5cff' },
      areaStyle: { color: 'rgba(124,92,255,0.18)' },
      data: days.map(d => d.total),
    }],
  }
})

const topBarOption = computed(() => {
  const keys = (top.value?.keys ?? []).slice().reverse()
  return {
    backgroundColor: 'transparent',
    grid: { left: 90, right: 30, top: 8, bottom: 24 },
    tooltip: {
      trigger: 'axis', axisPointer: { type: 'shadow' },
      backgroundColor: '#0f172a', borderColor: '#334155',
      textStyle: { color: '#e2e8f0' },
      formatter: (p: any) => {
        const it = p[0]
        return `${it.name}<br>${it.value.toLocaleString()} presses`
      },
    },
    xAxis: {
      type: 'value', axisLine: { show: false }, axisTick: { show: false },
      splitLine: { lineStyle: { color: '#1e293b' } },
      axisLabel: { color: '#94a3b8' },
    },
    yAxis: {
      type: 'category',
      data: keys.map(k => k.name.replace(/^VK_/, '')),
      axisLine: { show: false }, axisTick: { show: false },
      axisLabel: { color: '#cbd5e1' },
    },
    series: [{
      type: 'bar',
      data: keys.map(k => k.count),
      itemStyle: { color: '#7c5cff', borderRadius: [0, 4, 4, 0] },
      barWidth: '60%',
    }],
  }
})

const chartHeight = '300px'
</script>

<template>
  <div v-if="error" class="panel panel-pad text-red-300" role="alert">
    {{ error }}
  </div>

  <div v-else class="space-y-6">
    <!-- Status bar -->
    <div class="flex items-center justify-between text-xs text-slate-400 -mt-2">
      <div class="flex items-center gap-2">
        <span
          class="relative inline-flex w-2 h-2"
          :title="liveTick
            ? 'New presses since last refresh'
            : 'Daemon connected — no new presses since last refresh'"
          aria-hidden="true"
        >
          <span
            v-if="liveTick"
            class="absolute inset-0 rounded-full bg-emerald-400 animate-ping opacity-75"
          ></span>
          <span
            class="relative inline-block w-2 h-2 rounded-full"
            :class="liveTick ? 'bg-emerald-400' : 'bg-emerald-600/60'"
          ></span>
        </span>
        <span>
          {{ liveTick ? 'New activity' : 'Listening' }}
        </span>
      </div>
      <div class="flex items-center gap-3 tabular-nums">
        <span>flush every {{ summary?.flush_interval_seconds ?? '–' }}s</span>
        <span
          class="w-1.5 h-1.5 rounded-full"
          :class="refreshing ? 'bg-accent animate-pulse' : 'bg-slate-700'"
          :title="refreshing ? 'Refreshing…' : 'Idle between refreshes'"
          aria-hidden="true"
        ></span>
      </div>
    </div>

    <div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
      <StatCard
        label="Today"
        :value="summary?.today_total ?? 0"
        :hint="summary?.today"
        accent
      />
      <StatCard
        label="Session"
        :value="summary?.session_total ?? 0"
        hint="since daemon start"
      />
      <StatCard
        label="All time"
        :value="summary?.all_time_total ?? 0"
        :hint="summary?.first_recorded_date ? `since ${summary.first_recorded_date}` : ''"
      />
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <div class="panel panel-pad lg:col-span-2 flex flex-col">
        <div class="flex items-baseline justify-between mb-3">
          <div class="panel-title">Last 30 days</div>
          <div class="text-xs text-slate-400">total presses / day</div>
        </div>
        <ChartBox :option="sparkOption" :height="chartHeight" />
      </div>

      <div class="panel panel-pad flex flex-col">
        <div class="panel-title mb-3">Top keys today</div>
        <div
          v-if="!top?.keys.length"
          class="flex-1 grid place-items-center text-sm text-slate-400 py-12 text-center"
        >
          <div>
            <div class="text-3xl mb-2 opacity-40" aria-hidden="true">⌨</div>
            No data yet — keep typing.
          </div>
        </div>
        <ChartBox v-else :option="topBarOption" :height="chartHeight" />
      </div>
    </div>

    <div v-if="loading" class="text-xs text-slate-400" role="status">
      loading…
    </div>
  </div>
</template>
