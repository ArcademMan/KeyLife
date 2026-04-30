<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { api } from '../api'
import { useRangeStore } from '../stores/range'
import type { AppCount, AppsHourly, AppsSummary, PerAppSettings } from '../types'

const data = ref<AppsSummary | null>(null)
const settings = ref<PerAppSettings | null>(null)
const error = ref<string | null>(null)
const loading = ref(true)

const range = useRangeStore()
const { params } = storeToRefs(range)

async function load(): Promise<void> {
  try {
    loading.value = true
    const [s, d] = await Promise.all([
      settings.value ? Promise.resolve(settings.value) : api.perAppSettings(),
      api.appsSummary({ ...params.value, limit: 50 }),
    ])
    settings.value = s
    data.value = d
    error.value = null
  } catch (e: any) {
    error.value = e?.message ?? 'failed to load'
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(params, () => {
  // Range changes invalidate the hourly cache: i conteggi delle ore sono
  // calcolati sul range, riusarli su un range diverso sarebbe sbagliato.
  hourlyCache.value = {}
  load()
}, { deep: true })

// Live polling, identico al pattern di KeyboardView: trigger su bump di
// all_time_total invece che ogni N secondi cieco, così evitiamo reload
// inutili quando non c'è attività.
const lastAllTime = ref<number | null>(null)
const pollSec = ref<number>(60)
let pollTimer: number | undefined

async function poll(): Promise<void> {
  if (document.hidden) return
  try {
    const s = await api.summary()
    pollSec.value = s.flush_interval_seconds
    if (lastAllTime.value !== null && s.all_time_total > lastAllTime.value) {
      data.value = await api.appsSummary({ ...params.value, limit: 50 })
      // Se l'utente sta guardando un'app espansa, aggiorna anche quella
      // così i nuovi presses si vedono nelle barre.
      if (expandedExe.value) {
        await fetchHourly(expandedExe.value, true)
      }
    }
    lastAllTime.value = s.all_time_total
  } catch { /* swallow */ }
}

watch(pollSec, (sec) => {
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = window.setInterval(poll, Math.max(sec * 1000, 2000))
}, { immediate: true })

onMounted(() => {
  poll()
  document.addEventListener('visibilitychange', poll)
})
onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer)
  document.removeEventListener('visibilitychange', poll)
})

const apps = computed<AppCount[]>(() => data.value?.apps ?? [])
const total = computed(() => apps.value.reduce((s, a) => s + a.count, 0))
const maxCount = computed(() => apps.value[0]?.count ?? 0)

function pct(n: number): number {
  return total.value === 0 ? 0 : Math.round((n / total.value) * 1000) / 10
}

function barWidth(n: number): string {
  if (maxCount.value === 0) return '0%'
  return `${(n / maxCount.value) * 100}%`
}

function iconUrl(exe: string): string {
  return api.appIconUrl(exe)
}

const FALLBACK_ICON_DATA = (() => {
  const svg = `<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'>
    <rect x='2' y='2' width='28' height='28' rx='6' fill='%23334155'/>
    <text x='16' y='22' font-family='ui-sans-serif' font-size='14'
          fill='%23cbd5e1' text-anchor='middle'>?</text>
  </svg>`
  return `data:image/svg+xml;utf8,${svg.replace(/\s+/g, ' ').trim()}`
})()

function onIconError(e: Event): void {
  const img = e.target as HTMLImageElement
  if (img.src !== FALLBACK_ICON_DATA) img.src = FALLBACK_ICON_DATA
}

const trackingOff = computed(() => settings.value?.tracking_enabled === false)

// --- Expand: hourly profile per app -----------------------------------

interface HourlyState {
  loading: boolean
  error: string | null
  // 24 valori, indice = ora del giorno locale, somma su tutti i giorni del range.
  byHour: number[]
}

const expandedExe = ref<string | null>(null)
// Cache per exe → invalidata al cambio di range (vedi watch params sopra).
const hourlyCache = ref<Record<string, HourlyState>>({})

async function toggleExpand(exe: string): Promise<void> {
  if (expandedExe.value === exe) {
    expandedExe.value = null
    return
  }
  expandedExe.value = exe
  if (!hourlyCache.value[exe]) {
    await fetchHourly(exe, false)
  }
}

async function fetchHourly(exe: string, refresh: boolean): Promise<void> {
  if (!refresh && hourlyCache.value[exe]?.byHour) return
  hourlyCache.value = {
    ...hourlyCache.value,
    [exe]: { loading: true, error: null, byHour: hourlyCache.value[exe]?.byHour ?? [] },
  }
  try {
    const r: AppsHourly = await api.appsHourly({ ...params.value, exe_name: exe })
    const byHour = new Array<number>(24).fill(0)
    for (const c of r.cells) {
      if (c.hour >= 0 && c.hour < 24) byHour[c.hour] += c.count
    }
    hourlyCache.value = {
      ...hourlyCache.value,
      [exe]: { loading: false, error: null, byHour },
    }
  } catch (e: any) {
    hourlyCache.value = {
      ...hourlyCache.value,
      [exe]: {
        loading: false,
        error: e?.message ?? 'failed to load hourly profile',
        byHour: [],
      },
    }
  }
}

function profileFor(exe: string): HourlyState | null {
  return hourlyCache.value[exe] ?? null
}

function profileMax(byHour: number[]): number {
  let m = 0
  for (const v of byHour) if (v > m) m = v
  return m
}

function profileTotal(byHour: number[]): number {
  let t = 0
  for (const v of byHour) t += v
  return t
}

function peakHour(byHour: number[]): number | null {
  let max = -1
  let arg = -1
  for (let i = 0; i < byHour.length; i++) {
    if (byHour[i] > max) { max = byHour[i]; arg = i }
  }
  return max > 0 ? arg : null
}

function fmtHour(h: number): string {
  return `${String(h).padStart(2, '0')}:00`
}

// Bucket sintetici dal backend (es. `<no app>`): exe_name che iniziano
// con `<` non sono path Windows validi → impossibile collisione con un
// exe reale. Li renderizziamo italic + tooltip esplicativo.
function isSynthetic(exe: string): boolean {
  return exe.startsWith('<')
}

function tooltipFor(exe: string): string {
  if (exe === '<no app>') {
    return 'Press registrati senza attribuzione: prima di abilitare il tracking per-app, durante periodi off, o per app in blocklist.'
  }
  return exe
}
</script>

<template>
  <div class="space-y-6">
    <!-- Tracking off banner -->
    <div
      v-if="trackingOff"
      class="panel panel-pad border border-amber-500/40 bg-amber-500/5"
    >
      <div class="flex items-start gap-3">
        <span class="text-amber-400 text-xl leading-none" aria-hidden="true">!</span>
        <div class="space-y-1">
          <div class="font-medium text-slate-100">Per-application tracking is off</div>
          <p class="text-sm text-slate-400">
            Enable it from
            <RouterLink to="/settings" class="text-accent hover:underline">Settings</RouterLink>
            to start collecting per-application keystroke counts. Existing
            data (if any) shown below was recorded while tracking was active.
          </p>
        </div>
      </div>
    </div>

    <div v-if="error" class="panel panel-pad text-red-300" role="alert">
      {{ error }}
    </div>

    <div
      v-else-if="loading && !data"
      class="panel panel-pad text-slate-400"
    >
      Loading…
    </div>

    <div
      v-else-if="apps.length === 0"
      class="panel panel-pad text-slate-400"
    >
      No application activity recorded for the selected range.
    </div>

    <section v-else class="space-y-3">
      <header class="flex items-baseline justify-between">
        <h2 class="text-base font-semibold text-slate-100">
          Applications
        </h2>
        <div class="text-sm text-slate-400 tabular-nums">
          {{ apps.length }} apps •
          <span class="text-slate-200">{{ total.toLocaleString() }}</span>
          presses tracked
        </div>
      </header>

      <ul class="panel divide-y divide-slate-800">
        <li
          v-for="app in apps"
          :key="app.exe_name"
          class="block"
        >
          <button
            type="button"
            class="w-full flex items-center gap-4 px-4 py-3 text-left
                   hover:bg-slate-900/50 focus-visible:outline-none
                   focus-visible:ring-2 focus-visible:ring-accent/50 focus-visible:ring-inset"
            :aria-expanded="expandedExe === app.exe_name"
            :aria-controls="`hourly-panel-${app.exe_name}`"
            @click="toggleExpand(app.exe_name)"
          >
            <img
              :src="app.has_icon ? iconUrl(app.exe_name) : FALLBACK_ICON_DATA"
              :alt="''"
              class="w-8 h-8 shrink-0 rounded-sm bg-slate-900 object-contain"
              loading="lazy"
              decoding="async"
              @error="onIconError"
            />
            <div class="flex-1 min-w-0">
              <div class="flex items-baseline justify-between gap-2">
                <div
                  class="font-mono text-sm truncate"
                  :class="isSynthetic(app.exe_name) ? 'italic text-slate-400' : ''"
                  :title="tooltipFor(app.exe_name)"
                >
                  {{ app.exe_name }}
                </div>
                <div class="text-sm tabular-nums text-slate-300 shrink-0">
                  {{ app.count.toLocaleString() }}
                  <span class="text-slate-500">({{ pct(app.count) }}%)</span>
                </div>
              </div>
              <div class="mt-1 h-1.5 rounded-full bg-slate-800 overflow-hidden">
                <div
                  class="h-full bg-accent rounded-full"
                  :style="{ width: barWidth(app.count) }"
                ></div>
              </div>
            </div>
            <span
              class="text-slate-500 text-xs shrink-0 transition-transform duration-150"
              :class="expandedExe === app.exe_name ? 'rotate-90' : ''"
              aria-hidden="true"
            >▶</span>
          </button>

          <!-- Hourly profile panel (collapsed by default) -->
          <div
            v-if="expandedExe === app.exe_name"
            :id="`hourly-panel-${app.exe_name}`"
            class="px-4 pb-4 pt-1 bg-slate-950/40 border-t border-slate-800"
          >
            <div
              v-if="profileFor(app.exe_name)?.loading && !profileFor(app.exe_name)?.byHour.length"
              class="text-xs text-slate-400 py-3"
            >Loading hourly profile…</div>

            <div
              v-else-if="profileFor(app.exe_name)?.error"
              class="text-xs text-red-300 py-3"
              role="alert"
            >{{ profileFor(app.exe_name)?.error }}</div>

            <template v-else-if="profileFor(app.exe_name)">
              <div class="flex items-baseline justify-between mb-2 mt-3">
                <div class="text-xs text-slate-400">
                  Hour-of-day profile
                  <span class="text-slate-500">— summed across {{ data?.start }} → {{ data?.end }}</span>
                </div>
                <div class="text-xs text-slate-400 tabular-nums">
                  <template v-if="peakHour(profileFor(app.exe_name)!.byHour) !== null">
                    Peak <span class="text-slate-200">{{ fmtHour(peakHour(profileFor(app.exe_name)!.byHour)!) }}</span>
                    •
                  </template>
                  <span class="text-slate-200">
                    {{ profileTotal(profileFor(app.exe_name)!.byHour).toLocaleString() }}
                  </span>
                  presses
                </div>
              </div>

              <!-- 24-bar chart, fixed height. Bars use bg-accent with opacity. -->
              <div class="flex items-end gap-px h-20" role="img" aria-label="hour profile">
                <div
                  v-for="(c, h) in profileFor(app.exe_name)!.byHour"
                  :key="h"
                  class="flex-1 relative group"
                >
                  <div
                    class="w-full rounded-sm transition-colors"
                    :class="c > 0 ? 'bg-accent' : 'bg-slate-800'"
                    :style="{
                      height: c > 0
                        ? `${Math.max(6, (c / Math.max(1, profileMax(profileFor(app.exe_name)!.byHour))) * 100)}%`
                        : '4%',
                      opacity: c > 0 ? '0.95' : '0.4',
                    }"
                    :title="`${fmtHour(h)} — ${c.toLocaleString()} presses`"
                  ></div>
                </div>
              </div>

              <!-- Hour axis labels: every 3 hours -->
              <div class="flex gap-px mt-1 text-[10px] text-slate-500 tabular-nums">
                <div v-for="h in 24" :key="h-1" class="flex-1 text-center">
                  <span v-if="(h - 1) % 3 === 0">{{ String(h - 1).padStart(2, '0') }}</span>
                </div>
              </div>
            </template>
          </div>
        </li>
      </ul>
    </section>
  </div>
</template>
