<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../../api'
import type { AppCount, PerAppSettings } from '../../types'

const perApp = ref<PerAppSettings | null>(null)
const blocklistText = ref('')
const knownApps = ref<AppCount[]>([])
const busy = ref(false)
const error = ref<string | null>(null)
const notice = ref<string | null>(null)
const showDisclosure = ref(false)
const forgetTarget = ref('')

onMounted(async () => {
  try {
    perApp.value = await api.perAppSettings()
    blocklistText.value = perApp.value.blocklist.join('\n')
  } catch (e: any) {
    error.value = e?.message ?? 'failed to load per-app settings'
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
    showDisclosure.value = true
    return
  }
  await applyTracking(enabled)
}

async function applyTracking(enabled: boolean): Promise<void> {
  busy.value = true; error.value = null; notice.value = null
  try {
    perApp.value = await api.setPerAppSettings({ tracking_enabled: enabled })
    notice.value = enabled ? 'Per-app tracking enabled.' : 'Per-app tracking disabled.'
    showDisclosure.value = false
  } catch (e: any) {
    error.value = e?.message ?? 'failed to save'
  } finally {
    busy.value = false
  }
}

async function saveBlocklist(): Promise<void> {
  busy.value = true; error.value = null; notice.value = null
  try {
    const blocklist = parseBlocklist(blocklistText.value)
    perApp.value = await api.setPerAppSettings({ blocklist })
    blocklistText.value = perApp.value.blocklist.join('\n')
    notice.value = `Blocklist saved (${perApp.value.blocklist.length} entries).`
  } catch (e: any) {
    error.value = e?.message ?? 'failed to save blocklist'
  } finally {
    busy.value = false
  }
}

async function forgetSelected(): Promise<void> {
  const exe = forgetTarget.value.trim().toLowerCase()
  if (!exe) return
  if (!confirm(`Delete all recorded data for "${exe}"? This cannot be undone.`)) return
  busy.value = true; error.value = null; notice.value = null
  try {
    const r = await api.forgetApp(exe)
    notice.value = `Forgot ${r.exe_name}: ${r.rows_deleted} rows removed.`
    forgetTarget.value = ''
    await refreshKnownApps()
  } catch (e: any) {
    error.value = e?.message ?? 'failed to forget'
  } finally {
    busy.value = false
  }
}
</script>

<template>
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
          :disabled="busy"
          :class="busy ? 'opacity-50 cursor-not-allowed' : ''"
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
          <button type="button" class="btn" :disabled="busy" @click="applyTracking(true)">
            Confirm and enable
          </button>
          <button type="button" class="btn" :disabled="busy" @click="showDisclosure = false">
            Cancel
          </button>
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
          <button type="button" class="btn text-xs" :disabled="busy" @click="saveBlocklist">
            Save blocklist
          </button>
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
            :disabled="busy || !forgetTarget.trim()"
            @click="forgetSelected"
          >Forget</button>
        </div>
      </div>

      <div v-if="notice" class="text-xs text-emerald-300" role="status">{{ notice }}</div>
      <div v-if="error" class="text-xs text-red-300" role="alert">{{ error }}</div>
    </div>
  </section>
</template>
