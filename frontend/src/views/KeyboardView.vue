<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { api } from '../api'
import { useRangeStore } from '../stores/range'
import type { KeyboardHeatmap, KeyboardLayout, LayoutKey } from '../types'
import ChartBox from '../components/ChartBox.vue'
import { useHandmapStore, geometricHand } from '../stores/handmap'

const handmap = useHandmapStore()

const layout = ref<KeyboardLayout | null>(null)
const data = ref<KeyboardHeatmap | null>(null)
const error = ref<string | null>(null)
const loading = ref(true)

const range = useRangeStore()
const { params } = storeToRefs(range)

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

onMounted(load)
watch(params, load, { deep: true })

const KEY_UNIT_PX = 48
const KEY_GAP_PX = 4

const keyboardWidth = computed(() => layout.value ? layout.value.width * KEY_UNIT_PX : 0)
const keyboardHeight = computed(() => layout.value ? layout.value.height * KEY_UNIT_PX : 0)

interface Tally { exact: Map<string, number>; perVk: Map<number, number> }

const tallies = computed<Tally>(() => {
  const exact = new Map<string, number>()
  const perVk = new Map<number, number>()
  for (const k of data.value?.keys ?? []) {
    exact.set(`${k.vk}:${k.scancode}`, k.count)
    perVk.set(k.vk, (perVk.get(k.vk) ?? 0) + k.count)
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

function intensity(c: number): number {
  if (c <= 0 || maxCount.value <= 0) return 0
  // log scale so the long tail is still visible
  return Math.log1p(c) / Math.log1p(maxCount.value)
}

type RGB = [number, number, number]
interface Palette {
  id: string
  label: string
  stops: RGB[]
  // Optional per-palette override for text color, given the normalized
  // intensity t in (0, 1]. If omitted, the default luminance heuristic runs.
  textForT?: (t: number) => string
}

// Thermal: dark text everywhere except the deep-blue zone at the very bottom
// of the gradient. t < 0.12 covers only the [10,10,50] stop and the early
// fade toward [40,80,200] — once we're firmly in any visible blue, the user
// wants black text. Cyan, green, yellow, orange, red are all black.
const thermalTextForT = (t: number): string => (t < 0.12 ? '#fff' : '#0b1220')

const PALETTES: Palette[] = [
  { id: 'accent',  label: 'Accent (default)', stops: [[30, 41, 59], [124, 92, 255]] },
  { id: 'thermal', label: 'Thermal',          stops: [[10, 10, 50], [40, 80, 200], [0, 200, 220], [60, 220, 90], [255, 220, 50], [255, 80, 30], [200, 0, 40]], textForT: thermalTextForT },
  { id: 'viridis', label: 'Viridis',          stops: [[68, 1, 84], [59, 82, 139], [33, 145, 140], [94, 201, 98], [253, 231, 37]] },
  { id: 'plasma',  label: 'Plasma',           stops: [[13, 8, 135], [126, 3, 168], [204, 71, 120], [248, 149, 64], [240, 249, 33]] },
  { id: 'mono',    label: 'Mono',             stops: [[20, 20, 20], [240, 240, 240]] },
  { id: 'custom',  label: 'Custom',           stops: [[30, 41, 59], [255, 80, 30]] },
]

const STORAGE_KEY = 'keylife.heatmap.palette.v1'
const stored = (() => {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null') } catch { return null }
})()

const paletteId = ref<string>(stored?.id ?? 'accent')
const customCold = ref<string>(stored?.cold ?? '#1e293b')
const customHot  = ref<string>(stored?.hot  ?? '#ff5018')

function hexToRgb(hex: string): RGB {
  const h = hex.replace('#', '')
  const n = parseInt(h.length === 3 ? h.split('').map(c => c + c).join('') : h, 16)
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
}

const activeStops = computed<RGB[]>(() => {
  if (paletteId.value === 'custom') return [hexToRgb(customCold.value), hexToRgb(customHot.value)]
  return PALETTES.find(p => p.id === paletteId.value)?.stops ?? PALETTES[0].stops
})

function sampleStops(stops: RGB[], t: number): RGB {
  if (stops.length === 1) return stops[0]
  const clamped = Math.max(0, Math.min(1, t))
  const x = clamped * (stops.length - 1)
  const i = Math.floor(x)
  if (i >= stops.length - 1) return stops[stops.length - 1]
  const f = x - i
  const a = stops[i], b = stops[i + 1]
  return [
    Math.round(a[0] + (b[0] - a[0]) * f),
    Math.round(a[1] + (b[1] - a[1]) * f),
    Math.round(a[2] + (b[2] - a[2]) * f),
  ]
}

function bgFor(c: number): string {
  const t = intensity(c)
  const [r, g, b] = sampleStops(activeStops.value, t)
  return `rgb(${r} ${g} ${b})`
}

const gradientCss = computed(() => {
  const stops = activeStops.value
  const parts = stops.map((s, i) => `rgb(${s[0]} ${s[1]} ${s[2]}) ${(i / (stops.length - 1)) * 100}%`)
  return `linear-gradient(90deg, ${parts.join(', ')})`
})

function textColorFor(c: number): string {
  const t = intensity(c)
  if (t === 0) return '#cbd5e1'
  const palette = paletteId.value === 'custom'
    ? null
    : PALETTES.find(p => p.id === paletteId.value)
  if (palette?.textForT) return palette.textForT(t)
  const [r, g, b] = sampleStops(activeStops.value, t)
  const lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255
  if (lum > 0.62) return '#0b1220'
  if (lum > 0.35) return '#fff'
  return '#cbd5e1'
}

watch([paletteId, customCold, customHot], () => {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      id: paletteId.value, cold: customCold.value, hot: customHot.value,
    }))
  } catch { /* ignore quota / disabled storage */ }
})

function fmt(n: number) { return n.toLocaleString() }

const labelByExact = computed(() => {
  const map = new Map<string, string>()
  for (const k of layout.value?.keys ?? []) {
    if (k.vk != null && k.scancode != null) {
      map.set(`${k.vk}:${k.scancode}`, k.label)
    }
  }
  return map
})

const labelByVk = computed(() => {
  const map = new Map<number, string>()
  for (const k of layout.value?.keys ?? []) {
    if (k.vk != null && k.scancode == null && !map.has(k.vk)) {
      map.set(k.vk, k.label)
    }
  }
  return map
})

function displayName(vk: number, scancode: number, name: string): string {
  return labelByExact.value.get(`${vk}:${scancode}`)
    ?? labelByVk.value.get(vk)
    ?? name.replace(/^VK_/, '')
}

const search = ref('')

interface KeyRow {
  vk: number
  scancode: number
  rawName: string
  display: string
  count: number
  pct: number
}

const allKeyRows = computed<KeyRow[]>(() => {
  const tot = totalPresses.value
  const rows: KeyRow[] = (data.value?.keys ?? []).map(k => ({
    vk: k.vk,
    scancode: k.scancode,
    rawName: k.name,
    display: displayName(k.vk, k.scancode, k.name),
    count: k.count,
    pct: tot > 0 ? (k.count / tot) * 100 : 0,
  }))
  rows.sort((a, b) => b.count - a.count)
  return rows
})

const filteredKeyRows = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return allKeyRows.value
  return allKeyRows.value.filter(r =>
    r.display.toLowerCase().includes(q) ||
    r.rawName.toLowerCase().includes(q),
  )
})

// ─────────────────────────────────────────────────────────────────────────────
// Categorization (Win32 VK codes)

type Category =
  | 'Letters' | 'Digits' | 'Punctuation' | 'Space'
  | 'Modifiers' | 'Navigation' | 'Editing' | 'Function' | 'Other'

const MODIFIER_VKS = new Set([
  0x10, 0x11, 0x12, 0x14, 0x5B, 0x5C, 0x5D,
  0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5,
])

function categorize(vk: number): Category {
  if (vk >= 0x41 && vk <= 0x5A) return 'Letters'
  if ((vk >= 0x30 && vk <= 0x39) || (vk >= 0x60 && vk <= 0x69)) return 'Digits'
  if (vk === 0x20) return 'Space'
  if (MODIFIER_VKS.has(vk)) return 'Modifiers'
  if (vk >= 0x70 && vk <= 0x87) return 'Function'
  if (vk === 0x08 || vk === 0x09 || vk === 0x0D || vk === 0x1B) return 'Editing'
  if ((vk >= 0x21 && vk <= 0x28) || vk === 0x2D || vk === 0x2E) return 'Navigation'
  // OEM punctuation: ; = , - . / ` [ \ ] '  + numpad operators
  if (
    (vk >= 0xBA && vk <= 0xC0) ||
    (vk >= 0xDB && vk <= 0xDF) ||
    (vk >= 0x6A && vk <= 0x6F)
  ) return 'Punctuation'
  return 'Other'
}

const CATEGORY_ORDER: Category[] = [
  'Letters', 'Digits', 'Punctuation', 'Space',
  'Modifiers', 'Navigation', 'Editing', 'Function', 'Other',
]

const CATEGORY_COLORS: Record<Category, string> = {
  Letters:     '#7c5cff',
  Digits:      '#5b8cff',
  Punctuation: '#22d3ee',
  Space:       '#34d399',
  Modifiers:   '#f59e0b',
  Navigation:  '#fb7185',
  Editing:     '#a855f7',
  Function:    '#94a3b8',
  Other:       '#475569',
}

interface CategoryBucket { name: Category; value: number }

const categoryBuckets = computed<CategoryBucket[]>(() => {
  const sums = new Map<Category, number>()
  for (const k of data.value?.keys ?? []) {
    const cat = categorize(k.vk)
    sums.set(cat, (sums.get(cat) ?? 0) + k.count)
  }
  return CATEGORY_ORDER
    .map(c => ({ name: c, value: sums.get(c) ?? 0 }))
    .filter(b => b.value > 0)
})

const categoryPieOption = computed(() => ({
  backgroundColor: 'transparent',
  tooltip: {
    trigger: 'item',
    backgroundColor: '#0f172a', borderColor: '#334155',
    textStyle: { color: '#e2e8f0' },
    formatter: (p: any) =>
      `${p.name}<br><b>${p.value.toLocaleString()}</b> presses · ${p.percent}%`,
  },
  legend: {
    orient: 'vertical',
    right: 8, top: 'middle',
    textStyle: { color: '#cbd5e1', fontSize: 11 },
    itemWidth: 10, itemHeight: 10,
  },
  series: [{
    type: 'pie',
    radius: ['50%', '78%'],
    center: ['35%', '50%'],
    avoidLabelOverlap: true,
    itemStyle: { borderColor: '#0f172a', borderWidth: 2 },
    label: { show: false },
    labelLine: { show: false },
    data: categoryBuckets.value.map(b => ({
      ...b,
      itemStyle: { color: CATEGORY_COLORS[b.name] },
    })),
  }],
}))

// Modifier breakdown
interface ModRow { name: string; count: number; pct: number }

const modifierRows = computed<ModRow[]>(() => {
  const groups: Array<{ name: string; vks: number[] }> = [
    { name: 'Shift', vks: [0x10, 0xA0, 0xA1] },
    { name: 'Ctrl',  vks: [0x11, 0xA2, 0xA3] },
    { name: 'Alt',   vks: [0x12, 0xA4, 0xA5] },
    { name: 'Win',   vks: [0x5B, 0x5C] },
    { name: 'Caps',  vks: [0x14] },
  ]
  const tot = totalPresses.value
  return groups.map(g => {
    let count = 0
    for (const k of data.value?.keys ?? []) {
      if (g.vks.includes(k.vk)) count += k.count
    }
    return { name: g.name, count, pct: tot > 0 ? (count / tot) * 100 : 0 }
  }).filter(r => r.count > 0)
})

const totalModifierShare = computed(() => {
  return modifierRows.value.reduce((s, r) => s + r.pct, 0)
})

// Left vs right hand. Per-key assignment is taken from the user's handmap
// overrides if present, falling back to a geometric default. Keys assigned to
// "Both" — or that geometrically straddle the midline (the spacebar) — split
// proportionally so the bar reflects two-handed contribution.
interface HandRow { side: 'Left' | 'Right'; count: number; pct: number }

const handBreakdown = computed<HandRow[]>(() => {
  if (!layout.value) return []
  const layoutByExact = new Map<string, LayoutKey>()
  const layoutByVk = new Map<number, LayoutKey>()
  for (const k of layout.value.keys) {
    if (k.vk == null) continue
    if (k.scancode != null) layoutByExact.set(`${k.vk}:${k.scancode}`, k)
    else if (!layoutByVk.has(k.vk)) layoutByVk.set(k.vk, k)
  }

  const mid = layout.value.width / 2
  let left = 0, right = 0

  for (const k of data.value?.keys ?? []) {
    const lk = layoutByExact.get(`${k.vk}:${k.scancode}`) ?? layoutByVk.get(k.vk)
    if (!lk) continue
    const override = handmap.get(k.vk, k.scancode)
    const hand = override ?? geometricHand(lk.x, lk.w, layout.value.width)

    if (hand === 'L') {
      left += k.count
    } else if (hand === 'R') {
      right += k.count
    } else {
      // Both: split proportionally if the key body crosses the midline,
      // otherwise 50/50.
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
  const rows: HandRow[] = [
    { side: 'Left',  count: Math.round(left),  pct: (left  / tot) * 100 },
    { side: 'Right', count: Math.round(right), pct: (right / tot) * 100 },
  ]
  return rows.filter(r => r.count > 0)
})
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
      <div class="flex items-center gap-3 text-xs text-slate-300">
        <label class="flex items-center gap-2">
          <span class="text-slate-400">Palette</span>
          <select
            v-model="paletteId"
            class="bg-slate-800 border border-slate-700 rounded px-2 py-1 text-xs text-slate-100"
            aria-label="Heatmap palette"
          >
            <option v-for="p in PALETTES" :key="p.id" :value="p.id">{{ p.label }}</option>
          </select>
        </label>
        <template v-if="paletteId === 'custom'">
          <label class="flex items-center gap-1">
            <span class="text-slate-400">cold</span>
            <input type="color" v-model="customCold" class="h-6 w-8 rounded bg-transparent border border-slate-700 cursor-pointer" aria-label="Cold color" />
          </label>
          <label class="flex items-center gap-1">
            <span class="text-slate-400">hot</span>
            <input type="color" v-model="customHot" class="h-6 w-8 rounded bg-transparent border border-slate-700 cursor-pointer" aria-label="Hot color" />
          </label>
        </template>
        <div class="flex items-center gap-2">
          <span class="tabular-nums text-slate-400">0</span>
          <div class="h-2 w-40 rounded-full" :style="{ background: gradientCss }" aria-hidden="true"></div>
          <span class="tabular-nums text-slate-300">{{ fmt(maxCount) }}</span>
        </div>
      </div>
    </div>

    <div class="panel p-6 overflow-auto">
      <div
        v-if="layout"
        class="relative mx-auto"
        :style="{
          width: keyboardWidth + 'px',
          height: keyboardHeight + 'px',
        }"
      >
        <div
          v-for="k in layout.keys"
          :key="k.id"
          class="absolute rounded-md border border-slate-700/50 flex flex-col items-center justify-center text-center select-none transition-colors"
          :style="{
            left: (k.x * KEY_UNIT_PX + KEY_GAP_PX/2) + 'px',
            top: (k.y * KEY_UNIT_PX + KEY_GAP_PX/2) + 'px',
            width: ((k.w ?? 1) * KEY_UNIT_PX - KEY_GAP_PX) + 'px',
            height: ((k.h ?? 1) * KEY_UNIT_PX - KEY_GAP_PX) + 'px',
            background: bgFor(countFor(k)),
            color: textColorFor(countFor(k)),
          }"
          :title="k.label + (k.vk != null ? ` • ${fmt(countFor(k))}` : ' • not tracked')"
        >
          <div class="text-[11px] font-medium leading-none">{{ k.label }}</div>
          <div
            v-if="k.vk != null && countFor(k) > 0"
            class="text-[9px] opacity-80 mt-0.5 tabular-nums leading-none"
          >
            {{ fmt(countFor(k)) }}
          </div>
        </div>
      </div>
    </div>

    <!-- Breakdown: categories, modifiers, hands -->
    <div
      v-if="totalPresses > 0"
      class="grid grid-cols-1 lg:grid-cols-3 gap-6"
    >
      <div class="panel panel-pad lg:col-span-1">
        <div class="panel-title mb-3">By category</div>
        <ChartBox :option="categoryPieOption" height="240px" />
      </div>

      <div class="panel panel-pad lg:col-span-1">
        <div class="flex items-baseline justify-between mb-3">
          <div class="panel-title">Modifiers</div>
          <div class="text-xs text-slate-400 tabular-nums">
            {{ totalModifierShare.toFixed(1) }}% of all presses
          </div>
        </div>
        <div
          v-if="!modifierRows.length"
          class="text-sm text-slate-400 py-8 text-center"
        >
          No modifier presses in range.
        </div>
        <div v-else class="flex flex-col gap-2">
          <div v-for="r in modifierRows" :key="r.name" class="flex items-center gap-3 text-sm">
            <span class="w-12 text-slate-300">{{ r.name }}</span>
            <div class="flex-1 h-2 bg-slate-800 rounded-full overflow-hidden">
              <div
                class="h-full"
                :style="{
                  width: r.pct + '%',
                  background: '#f59e0b',
                }"
              ></div>
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

      <div class="panel panel-pad lg:col-span-1">
        <div class="panel-title mb-3">Left vs right hand</div>
        <div
          v-if="!handBreakdown.length"
          class="text-sm text-slate-400 py-8 text-center"
        >
          Layout missing — can't classify.
        </div>
        <template v-else>
          <div class="h-3 w-full rounded-full overflow-hidden flex bg-slate-800 mb-3">
            <div
              v-for="r in handBreakdown"
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
              v-for="r in handBreakdown"
              :key="r.side"
              class="flex items-center justify-between gap-3"
            >
              <div class="flex items-center gap-2">
                <span
                  class="w-2.5 h-2.5 rounded-sm"
                  :style="{
                    background: r.side === 'Left'
                      ? '#7c5cff'
                      : r.side === 'Right'
                        ? '#22d3ee'
                        : '#475569',
                  }"
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
    </div>

    <!-- All keys table -->
    <div class="panel panel-pad">
      <div class="flex items-baseline justify-between gap-3 mb-3 flex-wrap">
        <div>
          <div class="panel-title">All keys</div>
          <div class="text-xs text-slate-400 mt-0.5 tabular-nums">
            {{ filteredKeyRows.length }} of {{ allKeyRows.length }}
            tracked key{{ allKeyRows.length === 1 ? '' : 's' }}
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

      <div
        v-if="!allKeyRows.length"
        class="text-sm text-slate-400 py-8 text-center"
      >
        No data yet — keep typing.
      </div>
      <div
        v-else-if="!filteredKeyRows.length"
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
              v-for="(row, i) in filteredKeyRows"
              :key="row.vk + ':' + row.scancode"
              class="border-t border-slate-800 hover:bg-slate-800/40"
            >
              <td class="px-3 py-1.5 text-slate-500 tabular-nums">
                {{ i + 1 }}
              </td>
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
                    <div
                      class="h-full bg-accent"
                      :style="{ width: row.pct + '%' }"
                    ></div>
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

    <div v-if="loading" class="text-xs text-slate-400" role="status">
      loading…
    </div>
  </div>
</template>
