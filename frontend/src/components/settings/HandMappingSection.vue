<script setup lang="ts">
import { computed } from 'vue'
import type { KeyboardLayout, LayoutKey } from '../../types'
import { useHandmapStore, geometricHand, type Hand } from '../../stores/handmap'
import KeyboardGrid from '../KeyboardGrid.vue'

defineProps<{ layout: KeyboardLayout | null }>()

const handmap = useHandmapStore()

function effectiveHand(k: LayoutKey, layout: KeyboardLayout | null): Hand | null {
  if (k.vk == null || !layout) return null
  const ov = handmap.get(k.vk, k.scancode ?? null)
  if (ov) return ov
  return geometricHand(k.x, k.w, layout.width)
}

function isOverridden(k: LayoutKey): boolean {
  if (k.vk == null) return false
  return handmap.get(k.vk, k.scancode ?? null) !== undefined
}

// Override manuale: solo L o R. "Both" resta come default geometrico per i
// tasti che genuinamente attraversano il midline (spacebar) ma non è una
// scelta sensata da imporre a mano — le statistiche per mano contano un B
// come mezzo press a sinistra e mezzo a destra.
const CYCLE: Array<Hand | null> = [null, 'L', 'R']

function cycleKey(k: LayoutKey) {
  if (k.vk == null) return
  const cur = isOverridden(k) ? handmap.get(k.vk, k.scancode ?? null) ?? null : null
  const idx = CYCLE.indexOf(cur as Hand | null)
  const next = CYCLE[(idx + 1) % CYCLE.length]
  if (next == null) handmap.unset(k.vk, k.scancode ?? null)
  else handmap.set(k.vk, k.scancode ?? null, next)
}

function bgFor(k: LayoutKey, layout: KeyboardLayout | null): string {
  if (k.vk == null) return '#0f172a'
  const h = effectiveHand(k, layout)
  if (h === 'L') return '#7c5cff'
  if (h === 'R') return '#22d3ee'
  if (h === 'B') return 'linear-gradient(90deg, #7c5cff 50%, #22d3ee 50%)'
  return '#0f172a'
}

function textFor(k: LayoutKey, layout: KeyboardLayout | null): string {
  const h = effectiveHand(k, layout)
  if (h === 'L') return '#ffffff'
  if (h === 'R') return '#0b1220'
  if (h === 'B') return '#ffffff'
  return '#cbd5e1'
}

const stats = (layout: KeyboardLayout | null) => computed(() => {
  if (!layout) return { L: 0, R: 0, B: 0, total: 0 }
  let L = 0, R = 0, B = 0, total = 0
  for (const k of layout.keys) {
    if (k.vk == null) continue
    total++
    const h = effectiveHand(k, layout)
    if (h === 'L') L++
    else if (h === 'R') R++
    else if (h === 'B') B++
  }
  return { L, R, B, total }
})

const overrideCount = computed(() => Object.keys(handmap.overrides).length)

function fillFromGeometry(layout: KeyboardLayout | null) {
  if (!layout) return
  const next: Record<string, Hand> = {}
  for (const k of layout.keys) {
    if (k.vk == null) continue
    const h = geometricHand(k.x, k.w, layout.width)
    const key = k.scancode != null ? `${k.vk}:${k.scancode}` : `${k.vk}`
    next[key] = h
  }
  handmap.setMany(next)
}

function mirror(layout: KeyboardLayout | null) {
  if (!layout) return
  const ov = handmap.overrides
  const next: Record<string, Hand> = {}
  for (const [k, v] of Object.entries(ov)) {
    next[k] = v === 'L' ? 'R' : v === 'R' ? 'L' : v
  }
  handmap.resetAll()
  handmap.setMany(next)
}
</script>

<template>
  <section class="space-y-4">
    <div>
      <h2 class="text-base font-semibold text-slate-100">Hand mapping</h2>
      <p class="text-sm text-slate-400 mt-1">
        Click a key to cycle through
        <span class="text-slate-200">Default</span> →
        <span class="text-[#7c5cff]">Left</span> →
        <span class="text-[#22d3ee]">Right</span>.
        The default uses the geometric midline of the layout; keys that
        straddle it (like the spacebar) keep a <span class="text-slate-200">Both</span>
        default that can't be set manually.
      </p>
    </div>

    <div class="panel panel-pad flex flex-wrap gap-6 items-center justify-between">
      <div class="flex flex-wrap gap-6 text-sm">
        <div>
          <div class="panel-title">Left</div>
          <div class="mt-1 text-2xl font-bold text-[#7c5cff] tabular-nums">
            {{ stats(layout).value.L }}
          </div>
        </div>
        <div>
          <div class="panel-title">Right</div>
          <div class="mt-1 text-2xl font-bold text-[#22d3ee] tabular-nums">
            {{ stats(layout).value.R }}
          </div>
        </div>
        <div>
          <div class="panel-title">Both</div>
          <div class="mt-1 text-2xl font-bold text-slate-100 tabular-nums">
            {{ stats(layout).value.B }}
          </div>
        </div>
        <div>
          <div class="panel-title">Overrides</div>
          <div class="mt-1 text-2xl font-bold text-slate-100 tabular-nums">
            {{ overrideCount }}
          </div>
          <div class="text-[10px] text-slate-500">user-defined</div>
        </div>
      </div>

      <div class="flex flex-wrap gap-2">
        <button
          type="button"
          class="btn text-xs"
          @click="fillFromGeometry(layout)"
          title="Persist geometric defaults as explicit overrides for every key"
        >
          Seed from geometry
        </button>
        <button
          type="button"
          class="btn text-xs"
          :disabled="!overrideCount"
          :class="!overrideCount ? 'opacity-50 cursor-not-allowed' : ''"
          @click="mirror(layout)"
          title="Swap Left↔Right on all current overrides"
        >
          Mirror L ↔ R
        </button>
        <button
          type="button"
          class="btn text-xs"
          :disabled="!overrideCount"
          :class="!overrideCount ? 'opacity-50 cursor-not-allowed' : ''"
          @click="handmap.resetAll()"
          title="Remove all overrides; revert to geometric defaults"
        >
          Reset all
        </button>
      </div>
    </div>

    <div class="panel p-6 overflow-auto">
      <KeyboardGrid v-if="layout" :layout="layout">
        <template #cell="{ keyDef, style }">
          <button
            type="button"
            :disabled="keyDef.vk == null"
            class="absolute rounded-md flex flex-col items-center justify-center
                   text-center select-none transition-colors
                   focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white"
            :class="[
              keyDef.vk == null
                ? 'border border-slate-800 cursor-default'
                : 'border border-slate-700/40 hover:brightness-110 cursor-pointer',
              isOverridden(keyDef) ? 'ring-2 ring-amber-400/70' : '',
            ]"
            :style="{
              ...style,
              background: bgFor(keyDef, layout),
              color: textFor(keyDef, layout),
            }"
            :aria-label="keyDef.label + (isOverridden(keyDef) ? ' (overridden)' : '') +
                         (effectiveHand(keyDef, layout) ? ' — ' + effectiveHand(keyDef, layout) : '')"
            :title="keyDef.label + (keyDef.vk == null
              ? ' • not tracked'
              : ' • ' + (isOverridden(keyDef) ? 'override: ' : 'default: ') +
                (effectiveHand(keyDef, layout) ?? '—'))"
            @click="cycleKey(keyDef)"
          >
            <div class="text-[11px] font-medium leading-none">{{ keyDef.label }}</div>
            <div
              v-if="keyDef.vk != null"
              class="text-[9px] opacity-80 mt-0.5 leading-none"
            >
              {{ effectiveHand(keyDef, layout) ?? '·' }}
            </div>
          </button>
        </template>
      </KeyboardGrid>
    </div>

    <div class="text-xs text-slate-500 flex items-center gap-3 flex-wrap">
      <span class="flex items-center gap-1.5">
        <span class="w-2.5 h-2.5 rounded-sm bg-[#7c5cff]" aria-hidden="true"></span>
        Left
      </span>
      <span class="flex items-center gap-1.5">
        <span class="w-2.5 h-2.5 rounded-sm bg-[#22d3ee]" aria-hidden="true"></span>
        Right
      </span>
      <span class="flex items-center gap-1.5">
        <span
          class="w-2.5 h-2.5 rounded-sm"
          style="background: linear-gradient(90deg, #7c5cff 50%, #22d3ee 50%);"
          aria-hidden="true"
        ></span>
        Both
      </span>
      <span class="flex items-center gap-1.5">
        <span class="w-2.5 h-2.5 rounded-sm ring-2 ring-amber-400/70 bg-slate-900"
              aria-hidden="true"></span>
        User override
      </span>
    </div>
  </section>
</template>
