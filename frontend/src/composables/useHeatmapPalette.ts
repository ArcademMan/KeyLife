import { computed, ref, watch, type ComputedRef, type Ref } from 'vue'
import { safeLoadJSON, safeSaveJSON } from '../lib/storage'

type RGB = [number, number, number]

interface Palette {
  id: string
  label: string
  stops: RGB[]
  // Optional per-palette override for text color given normalized intensity
  // t ∈ (0, 1]. If omitted, the default luminance heuristic runs.
  textForT?: (t: number) => string
}

// Thermal: dark text everywhere except the deep-blue zone at the very
// bottom. t < 0.12 covers the [10,10,50] stop and the early fade toward
// [40,80,200] — once we're firmly in any visible blue, black wins.
const thermalTextForT = (t: number): string => (t < 0.12 ? '#fff' : '#0b1220')

export const PALETTES: Palette[] = [
  { id: 'accent',  label: 'Accent (default)', stops: [[30, 41, 59], [124, 92, 255]] },
  { id: 'thermal', label: 'Thermal',          stops: [[10, 10, 50], [40, 80, 200], [0, 200, 220], [60, 220, 90], [255, 220, 50], [255, 80, 30], [200, 0, 40]], textForT: thermalTextForT },
  { id: 'viridis', label: 'Viridis',          stops: [[68, 1, 84], [59, 82, 139], [33, 145, 140], [94, 201, 98], [253, 231, 37]] },
  { id: 'plasma',  label: 'Plasma',           stops: [[13, 8, 135], [126, 3, 168], [204, 71, 120], [248, 149, 64], [240, 249, 33]] },
  { id: 'mono',    label: 'Mono',             stops: [[20, 20, 20], [240, 240, 240]] },
  { id: 'custom',  label: 'Custom',           stops: [[30, 41, 59], [255, 80, 30]] },
]

interface PersistedPalette {
  id: string
  cold: string
  hot: string
}

const STORAGE_KEY = 'keylife.heatmap.palette.v1'
const DEFAULTS: PersistedPalette = { id: 'accent', cold: '#1e293b', hot: '#ff5018' }

function hexToRgb(hex: string): RGB {
  const h = hex.replace('#', '')
  const n = parseInt(h.length === 3 ? h.split('').map(c => c + c).join('') : h, 16)
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
}

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

export interface HeatmapPaletteApi {
  paletteId: Ref<string>
  customCold: Ref<string>
  customHot: Ref<string>
  activeStops: ComputedRef<RGB[]>
  gradientCss: ComputedRef<string>
  intensity: (c: number, max: number) => number
  bgFor: (c: number, max: number) => string
  textColorFor: (c: number, max: number) => string
}

export function useHeatmapPalette(): HeatmapPaletteApi {
  // All three fields persist together as a single JSON blob under the
  // historical storage key, so installs that upgrade keep their palette.
  const stored = safeLoadJSON<Partial<PersistedPalette>>(STORAGE_KEY) ?? {}
  const paletteId  = ref<string>(stored.id   ?? DEFAULTS.id)
  const customCold = ref<string>(stored.cold ?? DEFAULTS.cold)
  const customHot  = ref<string>(stored.hot  ?? DEFAULTS.hot)

  watch([paletteId, customCold, customHot], () => {
    safeSaveJSON(STORAGE_KEY, {
      id: paletteId.value,
      cold: customCold.value,
      hot: customHot.value,
    } satisfies PersistedPalette)
  })

  const activeStops = computed<RGB[]>(() => {
    if (paletteId.value === 'custom') return [hexToRgb(customCold.value), hexToRgb(customHot.value)]
    return PALETTES.find(p => p.id === paletteId.value)?.stops ?? PALETTES[0].stops
  })

  const gradientCss = computed(() => {
    const stops = activeStops.value
    const parts = stops.map((s, i) => `rgb(${s[0]} ${s[1]} ${s[2]}) ${(i / (stops.length - 1)) * 100}%`)
    return `linear-gradient(90deg, ${parts.join(', ')})`
  })

  // Log scale so the long tail of low-count keys is still visible.
  function intensity(c: number, max: number): number {
    if (c <= 0 || max <= 0) return 0
    return Math.log1p(c) / Math.log1p(max)
  }

  function bgFor(c: number, max: number): string {
    const t = intensity(c, max)
    const [r, g, b] = sampleStops(activeStops.value, t)
    return `rgb(${r} ${g} ${b})`
  }

  function textColorFor(c: number, max: number): string {
    const t = intensity(c, max)
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

  return { paletteId, customCold, customHot, activeStops, gradientCss, intensity, bgFor, textColorFor }
}
