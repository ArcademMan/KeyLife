<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import type { AppCount, KeyboardLayout, LayoutKey, PerAppSettings } from '../types'
import { useHandmapStore, geometricHand, type Hand } from '../stores/handmap'

const handmap = useHandmapStore()

const layout = ref<KeyboardLayout | null>(null)
const error = ref<string | null>(null)

// --- Per-app tracking state -------------------------------------------
const perApp = ref<PerAppSettings | null>(null)
const blocklistText = ref('')        // textarea content, one entry per line
const knownApps = ref<AppCount[]>([])  // popolato per la dropdown "Forget"
const perAppBusy = ref(false)
const perAppError = ref<string | null>(null)
const perAppNotice = ref<string | null>(null)
const showDisclosure = ref(false)
const forgetTarget = ref('')

onMounted(async () => {
  try {
    const [l, p] = await Promise.all([api.layout(), api.perAppSettings()])
    layout.value = l
    perApp.value = p
    blocklistText.value = p.blocklist.join('\n')
  } catch (e: any) {
    error.value = e?.message ?? 'failed to load settings'
  }
  refreshKnownApps()
})

async function refreshKnownApps(): Promise<void> {
  // Range largo per popolare la dropdown forget; ignoriamo errori.
  try {
    const today = new Date().toISOString().slice(0, 10)
    const start = '2000-01-01'
    const r = await api.appsSummary({ start, end: today, limit: 500 })
    knownApps.value = r.apps
  } catch { /* swallow */ }
}

function parseBlocklist(text: string): string[] {
  return text
    .split(/\r?\n/)
    .map(s => s.trim().toLowerCase())
    .filter(s => s.length > 0)
}

async function setTracking(enabled: boolean): Promise<void> {
  if (enabled && !perApp.value?.tracking_enabled) {
    // Apre la disclosure invece di accendere subito: l'utente conferma
    // dopo aver letto cosa viene salvato.
    showDisclosure.value = true
    return
  }
  await applyTracking(enabled)
}

async function applyTracking(enabled: boolean): Promise<void> {
  perAppBusy.value = true
  perAppError.value = null
  perAppNotice.value = null
  try {
    perApp.value = await api.setPerAppSettings({ tracking_enabled: enabled })
    perAppNotice.value = enabled ? 'Per-app tracking enabled.' : 'Per-app tracking disabled.'
    showDisclosure.value = false
  } catch (e: any) {
    perAppError.value = e?.message ?? 'failed to save'
  } finally {
    perAppBusy.value = false
  }
}

async function saveBlocklist(): Promise<void> {
  perAppBusy.value = true
  perAppError.value = null
  perAppNotice.value = null
  try {
    const blocklist = parseBlocklist(blocklistText.value)
    perApp.value = await api.setPerAppSettings({ blocklist })
    blocklistText.value = perApp.value.blocklist.join('\n')
    perAppNotice.value = `Blocklist saved (${perApp.value.blocklist.length} entries).`
  } catch (e: any) {
    perAppError.value = e?.message ?? 'failed to save blocklist'
  } finally {
    perAppBusy.value = false
  }
}

async function forgetSelected(): Promise<void> {
  const exe = forgetTarget.value.trim().toLowerCase()
  if (!exe) return
  if (!confirm(`Delete all recorded data for "${exe}"? This cannot be undone.`)) return
  perAppBusy.value = true
  perAppError.value = null
  perAppNotice.value = null
  try {
    const r = await api.forgetApp(exe)
    perAppNotice.value = `Forgot ${r.exe_name}: ${r.rows_deleted} rows removed.`
    forgetTarget.value = ''
    await refreshKnownApps()
  } catch (e: any) {
    perAppError.value = e?.message ?? 'failed to forget'
  } finally {
    perAppBusy.value = false
  }
}

const KEY_UNIT_PX = 48
const KEY_GAP_PX = 4

const keyboardWidth = computed(() => layout.value ? layout.value.width * KEY_UNIT_PX : 0)
const keyboardHeight = computed(() => layout.value ? layout.value.height * KEY_UNIT_PX : 0)

// Effective resolution: override if set, else geometric default.
function effectiveHand(k: LayoutKey): Hand | null {
  if (k.vk == null || !layout.value) return null
  const ov = handmap.get(k.vk, k.scancode ?? null)
  if (ov) return ov
  return geometricHand(k.x, k.w, layout.value.width)
}

function isOverridden(k: LayoutKey): boolean {
  if (k.vk == null) return false
  return handmap.get(k.vk, k.scancode ?? null) !== undefined
}

// Override manuale: solo L o R. "Both" resta come default geometrico per i
// tasti che genuinamente attraversano il midline (spacebar) ma non è una
// scelta sensata da imporre a mano — le statistiche per mano contano un B
// come mezzo press a sinistra e mezzo a destra, e su un tasto non-spacebar
// è quasi sempre un errore di click.
const CYCLE: Array<Hand | null> = [null, 'L', 'R']

function cycleKey(k: LayoutKey) {
  if (k.vk == null) return
  const cur = isOverridden(k) ? handmap.get(k.vk, k.scancode ?? null) ?? null : null
  const idx = CYCLE.indexOf(cur as Hand | null)
  const next = CYCLE[(idx + 1) % CYCLE.length]
  if (next == null) handmap.unset(k.vk, k.scancode ?? null)
  else handmap.set(k.vk, k.scancode ?? null, next)
}

function bgFor(k: LayoutKey): string {
  if (k.vk == null) return '#0f172a'
  const h = effectiveHand(k)
  if (h === 'L') return '#7c5cff'
  if (h === 'R') return '#22d3ee'
  if (h === 'B') return 'linear-gradient(90deg, #7c5cff 50%, #22d3ee 50%)'
  return '#0f172a'
}

function textFor(k: LayoutKey): string {
  const h = effectiveHand(k)
  if (h === 'L') return '#ffffff'
  if (h === 'R') return '#0b1220'
  if (h === 'B') return '#ffffff'
  return '#cbd5e1'
}

const stats = computed(() => {
  if (!layout.value) return { L: 0, R: 0, B: 0, total: 0 }
  let L = 0, R = 0, B = 0, total = 0
  for (const k of layout.value.keys) {
    if (k.vk == null) continue
    total++
    const h = effectiveHand(k)
    if (h === 'L') L++
    else if (h === 'R') R++
    else if (h === 'B') B++
  }
  return { L, R, B, total }
})

const overrideCount = computed(() => Object.keys(handmap.overrides).length)

function fillFromGeometry() {
  if (!layout.value) return
  const next: Record<string, Hand> = {}
  for (const k of layout.value.keys) {
    if (k.vk == null) continue
    const h = geometricHand(k.x, k.w, layout.value.width)
    const key = k.scancode != null ? `${k.vk}:${k.scancode}` : `${k.vk}`
    next[key] = h
  }
  handmap.setMany(next)
}

function mirror() {
  // Swap L↔R for all current overrides; B stays.
  if (!layout.value) return
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
  <div v-if="error" class="panel panel-pad text-red-300" role="alert">
    {{ error }}
  </div>

  <div v-else class="space-y-6">
    <!-- Section: Hand mapping -->
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
              {{ stats.L }}
            </div>
          </div>
          <div>
            <div class="panel-title">Right</div>
            <div class="mt-1 text-2xl font-bold text-[#22d3ee] tabular-nums">
              {{ stats.R }}
            </div>
          </div>
          <div>
            <div class="panel-title">Both</div>
            <div class="mt-1 text-2xl font-bold text-slate-100 tabular-nums">
              {{ stats.B }}
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
            @click="fillFromGeometry"
            title="Persist geometric defaults as explicit overrides for every key"
          >
            Seed from geometry
          </button>
          <button
            type="button"
            class="btn text-xs"
            :disabled="!overrideCount"
            :class="!overrideCount ? 'opacity-50 cursor-not-allowed' : ''"
            @click="mirror"
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
        <div
          v-if="layout"
          class="relative mx-auto"
          :style="{
            width: keyboardWidth + 'px',
            height: keyboardHeight + 'px',
          }"
        >
          <button
            v-for="k in layout.keys"
            :key="k.id"
            type="button"
            :disabled="k.vk == null"
            class="absolute rounded-md flex flex-col items-center justify-center
                   text-center select-none transition-colors
                   focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white"
            :class="[
              k.vk == null
                ? 'border border-slate-800 cursor-default'
                : 'border border-slate-700/40 hover:brightness-110 cursor-pointer',
              isOverridden(k) ? 'ring-2 ring-amber-400/70' : '',
            ]"
            :style="{
              left: (k.x * KEY_UNIT_PX + KEY_GAP_PX/2) + 'px',
              top: (k.y * KEY_UNIT_PX + KEY_GAP_PX/2) + 'px',
              width: ((k.w ?? 1) * KEY_UNIT_PX - KEY_GAP_PX) + 'px',
              height: ((k.h ?? 1) * KEY_UNIT_PX - KEY_GAP_PX) + 'px',
              background: bgFor(k),
              color: textFor(k),
            }"
            :aria-label="k.label + (isOverridden(k) ? ' (overridden)' : '') +
                         (effectiveHand(k) ? ' — ' + effectiveHand(k) : '')"
            :title="k.label + (k.vk == null
              ? ' • not tracked'
              : ' • ' + (isOverridden(k) ? 'override: ' : 'default: ') +
                (effectiveHand(k) ?? '—'))"
            @click="cycleKey(k)"
          >
            <div class="text-[11px] font-medium leading-none">{{ k.label }}</div>
            <div
              v-if="k.vk != null"
              class="text-[9px] opacity-80 mt-0.5 leading-none"
            >
              {{ effectiveHand(k) ?? '·' }}
            </div>
          </button>
        </div>
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

    <!-- Section: Per-application tracking -->
    <section class="space-y-4">
      <div>
        <h2 class="text-base font-semibold text-slate-100">Per-application tracking</h2>
        <p class="text-sm text-slate-400 mt-1">
          When enabled, KeyLife also counts how many keys you press in each
          foreground application (by executable name only — never window
          titles or full paths). Stored in the encrypted database; off by default.
        </p>
      </div>

      <div class="panel panel-pad space-y-4">
        <!-- Toggle -->
        <div class="flex items-center justify-between gap-4">
          <div>
            <div class="font-medium">
              {{ perApp?.tracking_enabled ? 'Tracking is on' : 'Tracking is off' }}
            </div>
            <p class="text-xs text-slate-400 mt-0.5">
              {{ perApp?.tracking_enabled
                ? 'Foreground app changes are recorded; toggle off to stop.'
                : 'Toggle on to start recording per-app keystroke counts.' }}
            </p>
          </div>
          <button
            type="button"
            class="btn"
            :disabled="perAppBusy"
            :class="perAppBusy ? 'opacity-50 cursor-not-allowed' : ''"
            @click="setTracking(!perApp?.tracking_enabled)"
          >
            {{ perApp?.tracking_enabled ? 'Turn off' : 'Turn on…' }}
          </button>
        </div>

        <!-- Disclosure dialog (inline) -->
        <div
          v-if="showDisclosure"
          class="rounded-md border border-amber-500/40 bg-amber-500/5 p-4 text-sm"
        >
          <div class="font-medium text-slate-100 mb-2">
            Before turning on per-application tracking
          </div>
          <ul class="list-disc list-inside space-y-1 text-slate-300">
            <li>Only the executable filename is stored (e.g. <code>chrome.exe</code>).</li>
            <li>Window titles and full paths are <strong>never</strong> recorded.</li>
            <li>Data lives in the encrypted database; the key is in Windows Credential Manager.</li>
            <li>You can add specific apps to a blocklist below, or "Forget app" to wipe one's history.</li>
          </ul>
          <div class="mt-3 flex gap-2">
            <button
              type="button"
              class="btn"
              :disabled="perAppBusy"
              @click="applyTracking(true)"
            >Confirm and enable</button>
            <button
              type="button"
              class="btn"
              :disabled="perAppBusy"
              @click="showDisclosure = false"
            >Cancel</button>
          </div>
        </div>

        <!-- Blocklist -->
        <div class="space-y-2">
          <label class="block">
            <span class="text-sm font-medium">Blocklist</span>
            <span class="text-xs text-slate-400 ml-2">
              one executable name per line — case-insensitive, exact match
            </span>
          </label>
          <textarea
            v-model="blocklistText"
            rows="5"
            spellcheck="false"
            placeholder="signal.exe&#10;banking-app.exe"
            class="w-full font-mono text-sm rounded-md bg-slate-950 border border-slate-800
                   px-3 py-2 outline-none focus:border-accent"
          ></textarea>
          <div class="flex justify-end">
            <button
              type="button"
              class="btn text-xs"
              :disabled="perAppBusy"
              @click="saveBlocklist"
            >Save blocklist</button>
          </div>
        </div>

        <!-- Forget app -->
        <div class="space-y-2 border-t border-slate-800 pt-4">
          <label class="block">
            <span class="text-sm font-medium">Forget an application</span>
            <span class="text-xs text-slate-400 ml-2">
              wipes daily, hourly, and icon rows for that exe
            </span>
          </label>
          <div class="flex gap-2">
            <input
              v-model="forgetTarget"
              list="known-apps-list"
              placeholder="exe name…"
              spellcheck="false"
              class="flex-1 font-mono text-sm rounded-md bg-slate-950 border border-slate-800
                     px-3 py-2 outline-none focus:border-accent"
            />
            <datalist id="known-apps-list">
              <option
                v-for="app in knownApps"
                :key="app.exe_name"
                :value="app.exe_name"
              />
            </datalist>
            <button
              type="button"
              class="btn text-xs"
              :disabled="perAppBusy || !forgetTarget.trim()"
              @click="forgetSelected"
            >Forget</button>
          </div>
        </div>

        <div
          v-if="perAppNotice"
          class="text-xs text-emerald-300"
          role="status"
        >{{ perAppNotice }}</div>
        <div
          v-if="perAppError"
          class="text-xs text-red-300"
          role="alert"
        >{{ perAppError }}</div>
      </div>
    </section>
  </div>
</template>
