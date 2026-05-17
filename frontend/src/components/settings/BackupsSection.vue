<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../../api'
import type { BackupConfig, BackupInfo } from '../../types'
import { fmtBytes, relativeTimeAgo } from '../../lib/date'

const cfg = ref<BackupConfig | null>(null)
const backups = ref<BackupInfo[]>([])
const busy = ref(false)
const error = ref<string | null>(null)
const notice = ref<string | null>(null)

// Draft values for the form fields. We don't bind directly to cfg so the
// user can cancel a change without immediate side effect.
const draftEnabled = ref(false)
const draftInterval = ref(24)
const draftKeep = ref(7)
const draftDir = ref('')      // empty string → default

// Passphrase modals: one for set (when has_passphrase=false), one for
// change (requires old), one for delete (requires current).
type Modal = null | 'set' | 'change' | 'delete' | 'restore'
const modal = ref<Modal>(null)
const newPp = ref('')
const newPp2 = ref('')
const oldPp = ref('')
const restoreFile = ref<File | null>(null)
const restorePp = ref('')

onMounted(reload)

async function reload(): Promise<void> {
  try {
    cfg.value = await api.backupConfig()
    backups.value = await api.listBackups()
    syncDraftFromConfig()
    error.value = null
  } catch (e: any) {
    error.value = e?.message ?? 'failed to load backup settings'
  }
}

function syncDraftFromConfig(): void {
  if (!cfg.value) return
  draftEnabled.value = cfg.value.enabled
  draftInterval.value = cfg.value.interval_hours
  draftKeep.value = cfg.value.keep_n
  draftDir.value = cfg.value.dir ?? ''
}

const draftDirty = computed(() => {
  if (!cfg.value) return false
  return draftEnabled.value !== cfg.value.enabled
    || draftInterval.value !== cfg.value.interval_hours
    || draftKeep.value !== cfg.value.keep_n
    || (draftDir.value || null) !== cfg.value.dir
})

const canEnable = computed(() => cfg.value?.has_passphrase === true)

function setNotice(msg: string): void {
  notice.value = msg
  window.setTimeout(() => { if (notice.value === msg) notice.value = null }, 4000)
}

function setError(e: any): void {
  // Axios normalizza l'errore con response.data.detail dal backend.
  const detail = e?.response?.data?.detail
  error.value = typeof detail === 'string' ? detail : (e?.message ?? 'request failed')
}

async function saveSettings(): Promise<void> {
  if (!cfg.value || busy.value) return
  busy.value = true; error.value = null
  try {
    cfg.value = await api.setBackupConfig({
      enabled: draftEnabled.value,
      interval_hours: draftInterval.value,
      keep_n: draftKeep.value,
      // null sentinel: il backend interpreta null/"" come "reset al default".
      dir: draftDir.value.trim() || null,
    })
    syncDraftFromConfig()
    setNotice('Settings saved.')
  } catch (e) {
    setError(e)
  } finally {
    busy.value = false
  }
}

function closeModal(): void {
  modal.value = null
  newPp.value = ''; newPp2.value = ''; oldPp.value = ''
  restoreFile.value = null; restorePp.value = ''
}

async function submitPassphraseSet(): Promise<void> {
  if (newPp.value.length < 8) { error.value = 'passphrase must be at least 8 characters'; return }
  if (newPp.value !== newPp2.value) { error.value = 'passphrases do not match'; return }
  busy.value = true; error.value = null
  try {
    cfg.value = await api.setBackupPassphrase(newPp.value)
    setNotice('Passphrase set. You can now enable auto-backup.')
    closeModal()
  } catch (e) { setError(e) }
  finally { busy.value = false }
}

async function submitPassphraseChange(): Promise<void> {
  if (newPp.value.length < 8) { error.value = 'new passphrase must be at least 8 characters'; return }
  if (newPp.value !== newPp2.value) { error.value = 'passphrases do not match'; return }
  if (!oldPp.value) { error.value = 'enter your current passphrase'; return }
  busy.value = true; error.value = null
  try {
    cfg.value = await api.setBackupPassphrase(newPp.value, oldPp.value)
    setNotice('Passphrase changed. New backups will use the new passphrase; existing .zip files keep the old one.')
    closeModal()
  } catch (e) { setError(e) }
  finally { busy.value = false }
}

async function submitPassphraseDelete(): Promise<void> {
  if (!oldPp.value) { error.value = 'enter your current passphrase'; return }
  if (!confirm('Remove the backup passphrase? Auto-backup will be disabled. Existing .zip files will still need the same passphrase to restore.')) return
  busy.value = true; error.value = null
  try {
    cfg.value = await api.deleteBackupPassphrase(oldPp.value)
    syncDraftFromConfig()
    setNotice('Passphrase removed.')
    closeModal()
  } catch (e) { setError(e) }
  finally { busy.value = false }
}

async function triggerBackup(): Promise<void> {
  if (busy.value) return
  busy.value = true; error.value = null
  try {
    const info = await api.backupNow()
    setNotice(`Backup created: ${info.filename} (${fmtBytes(info.size)}).`)
    await reload()
  } catch (e) { setError(e) }
  finally { busy.value = false }
}

async function deleteBackup(b: BackupInfo): Promise<void> {
  if (!confirm(`Delete ${b.filename}? This cannot be undone.`)) return
  busy.value = true; error.value = null
  try {
    await api.deleteBackup(b.filename)
    backups.value = backups.value.filter(x => x.filename !== b.filename)
    setNotice('Backup deleted.')
  } catch (e) { setError(e) }
  finally { busy.value = false }
}

function onFilePicked(e: Event): void {
  const input = e.target as HTMLInputElement
  restoreFile.value = input.files?.[0] ?? null
}

async function submitRestore(): Promise<void> {
  if (!restoreFile.value) { error.value = 'pick a backup .zip first'; return }
  if (!restorePp.value) { error.value = 'enter the passphrase used for that backup'; return }
  busy.value = true; error.value = null
  try {
    await api.restoreFromZip(restoreFile.value, restorePp.value)
    setNotice('Restore staged. Restart KeyLife to complete the restore. Your current DB will be saved as .pre-restore.bak.')
    closeModal()
    await reload()
  } catch (e) { setError(e) }
  finally { busy.value = false }
}

async function cancelStagedRestore(): Promise<void> {
  if (!confirm('Cancel the pending restore? The current DB will stay as it is.')) return
  busy.value = true; error.value = null
  try {
    await api.cancelRestore()
    setNotice('Restore cancelled.')
    await reload()
  } catch (e) { setError(e) }
  finally { busy.value = false }
}
</script>

<template>
  <section class="space-y-4">
    <div>
      <h2 class="text-base font-semibold text-slate-100">Backups</h2>
      <p class="text-sm text-slate-400 mt-1">
        Encrypted .zip backups of your database. The DB key is wrapped with a
        passphrase only you know, so backups are portable across machines as
        long as you remember the passphrase. Auto-backup runs on a schedule
        while the app is open.
      </p>
    </div>

    <!-- Restore-pending banner -->
    <div
      v-if="cfg?.restore_pending"
      class="panel panel-pad border border-amber-500/40 bg-amber-500/5"
    >
      <div class="flex items-start gap-3">
        <span class="text-amber-400 text-xl leading-none" aria-hidden="true">↻</span>
        <div class="flex-1 space-y-1">
          <div class="font-medium text-slate-100">Restore pending</div>
          <p class="text-sm text-slate-400">
            A restore was staged. Restart KeyLife to apply it; your current
            DB will be saved as <code>.pre-restore.bak</code>. You can also
            cancel and keep the current DB.
          </p>
          <button
            type="button"
            class="btn text-xs mt-2"
            :disabled="busy"
            @click="cancelStagedRestore"
          >Cancel restore</button>
        </div>
      </div>
    </div>

    <!-- Passphrase status -->
    <div class="panel panel-pad space-y-3">
      <div class="flex items-start justify-between gap-4">
        <div>
          <div class="font-medium text-slate-100">
            {{ cfg?.has_passphrase ? 'Backup passphrase is set' : 'No backup passphrase' }}
          </div>
          <p class="text-xs text-slate-400 mt-0.5">
            {{ cfg?.has_passphrase
              ? 'Required to read existing backups and create new ones. Store it somewhere safe — without it, your backups are useless.'
              : 'Set one before enabling auto-backup. The passphrase wraps the DB encryption key so backups are portable.' }}
          </p>
        </div>
        <div class="flex gap-2 shrink-0">
          <button
            v-if="!cfg?.has_passphrase"
            type="button"
            class="btn"
            :disabled="busy"
            @click="modal = 'set'"
          >Set passphrase</button>
          <template v-else>
            <button type="button" class="btn text-xs" :disabled="busy" @click="modal = 'change'">
              Change
            </button>
            <button type="button" class="btn text-xs" :disabled="busy" @click="modal = 'delete'">
              Remove
            </button>
          </template>
        </div>
      </div>
    </div>

    <!-- Auto-backup config -->
    <div class="panel panel-pad space-y-4">
      <div class="flex items-center justify-between gap-4">
        <div>
          <div class="font-medium text-slate-100">Auto-backup</div>
          <p class="text-xs text-slate-400 mt-0.5">
            Runs while the app is open. Last backup:
            <span class="text-slate-200">{{ relativeTimeAgo(cfg?.last_backup_at ?? null) }}</span>
          </p>
        </div>
        <label class="inline-flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            v-model="draftEnabled"
            :disabled="!canEnable"
            class="h-4 w-4 accent-accent"
          />
          <span class="text-sm" :class="canEnable ? 'text-slate-200' : 'text-slate-500'">
            {{ draftEnabled ? 'Enabled' : 'Disabled' }}
          </span>
        </label>
      </div>
      <p v-if="!canEnable" class="text-xs text-amber-400/80">
        Set a passphrase above to enable auto-backup.
      </p>

      <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <label class="block">
          <span class="text-xs text-slate-400">Interval (hours)</span>
          <input
            type="number"
            v-model.number="draftInterval"
            min="1" max="720"
            class="mt-1 w-full bg-slate-950 border border-slate-800 rounded-md
                   px-3 py-2 text-sm tabular-nums outline-none focus:border-accent"
          />
        </label>
        <label class="block">
          <span class="text-xs text-slate-400">Retention (keep last N)</span>
          <input
            type="number"
            v-model.number="draftKeep"
            min="1" max="365"
            class="mt-1 w-full bg-slate-950 border border-slate-800 rounded-md
                   px-3 py-2 text-sm tabular-nums outline-none focus:border-accent"
          />
        </label>
      </div>

      <label class="block">
        <span class="text-xs text-slate-400">Destination folder (leave empty for default)</span>
        <input
          v-model="draftDir"
          type="text"
          spellcheck="false"
          :placeholder="cfg?.resolved_dir ?? ''"
          class="mt-1 w-full font-mono text-xs bg-slate-950 border border-slate-800
                 rounded-md px-3 py-2 outline-none focus:border-accent"
        />
        <span class="text-[10px] text-slate-500 mt-1 block tabular-nums">
          current: {{ cfg?.resolved_dir }}
        </span>
      </label>

      <div class="flex justify-end">
        <button
          type="button"
          class="btn"
          :disabled="busy || !draftDirty"
          :class="!draftDirty ? 'opacity-50 cursor-not-allowed' : ''"
          @click="saveSettings"
        >Save</button>
      </div>
    </div>

    <!-- Existing backups + actions -->
    <div class="panel panel-pad space-y-3">
      <div class="flex items-center justify-between gap-2 flex-wrap">
        <div>
          <div class="font-medium text-slate-100">Existing backups</div>
          <p class="text-xs text-slate-400 mt-0.5">
            {{ backups.length }} file{{ backups.length === 1 ? '' : 's' }} in
            <code class="text-slate-300">{{ cfg?.resolved_dir ?? '…' }}</code>
          </p>
        </div>
        <div class="flex gap-2">
          <button
            type="button"
            class="btn"
            :disabled="busy || !cfg?.has_passphrase"
            :class="!cfg?.has_passphrase ? 'opacity-50 cursor-not-allowed' : ''"
            :title="!cfg?.has_passphrase ? 'Set a passphrase first' : ''"
            @click="triggerBackup"
          >Backup now</button>
          <button
            type="button"
            class="btn"
            :disabled="busy"
            @click="modal = 'restore'"
          >Restore from .zip…</button>
        </div>
      </div>

      <div v-if="backups.length === 0" class="text-sm text-slate-400 py-6 text-center">
        No backups yet. Click "Backup now" to create the first one.
      </div>
      <ul v-else class="divide-y divide-slate-800 -mx-2">
        <li
          v-for="b in backups"
          :key="b.filename"
          class="flex items-center gap-3 px-2 py-2 text-sm"
        >
          <div class="flex-1 min-w-0">
            <div class="font-mono text-xs truncate text-slate-200">{{ b.filename }}</div>
            <div class="text-[11px] text-slate-500 tabular-nums">
              {{ fmtBytes(b.size) }} · {{ relativeTimeAgo(b.created_at) }}
            </div>
          </div>
          <button
            type="button"
            class="btn text-xs"
            :disabled="busy"
            @click="deleteBackup(b)"
          >Delete</button>
        </li>
      </ul>
    </div>

    <div v-if="notice" class="text-xs text-emerald-300" role="status">{{ notice }}</div>
    <div v-if="error" class="text-xs text-red-300" role="alert">{{ error }}</div>

    <!-- Modals (inline, no portal lib) ----------------------------------- -->
    <div
      v-if="modal"
      class="fixed inset-0 z-30 bg-slate-950/70 backdrop-blur-sm
             flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      @click.self="closeModal"
    >
      <div class="w-full max-w-md panel panel-pad space-y-4">
        <!-- Set passphrase -->
        <template v-if="modal === 'set'">
          <h3 class="text-base font-semibold">Set backup passphrase</h3>
          <p class="text-xs text-slate-400">
            Choose a strong passphrase. There is no recovery: if you forget it,
            existing and future backups become unreadable.
          </p>
          <label class="block">
            <span class="text-xs text-slate-400">Passphrase (min 8 chars)</span>
            <input
              v-model="newPp"
              type="password"
              autocomplete="new-password"
              class="mt-1 w-full bg-slate-950 border border-slate-800 rounded-md
                     px-3 py-2 text-sm outline-none focus:border-accent"
            />
          </label>
          <label class="block">
            <span class="text-xs text-slate-400">Confirm</span>
            <input
              v-model="newPp2"
              type="password"
              autocomplete="new-password"
              class="mt-1 w-full bg-slate-950 border border-slate-800 rounded-md
                     px-3 py-2 text-sm outline-none focus:border-accent"
            />
          </label>
          <div class="flex justify-end gap-2">
            <button type="button" class="btn" :disabled="busy" @click="closeModal">Cancel</button>
            <button type="button" class="btn btn-accent" :disabled="busy" @click="submitPassphraseSet">
              Set passphrase
            </button>
          </div>
        </template>

        <!-- Change passphrase -->
        <template v-else-if="modal === 'change'">
          <h3 class="text-base font-semibold">Change backup passphrase</h3>
          <p class="text-xs text-slate-400">
            New backups will use the new passphrase. <strong>Existing .zip
            files keep the old passphrase</strong> — keep both somewhere safe
            until you're sure you no longer need the old backups.
          </p>
          <label class="block">
            <span class="text-xs text-slate-400">Current passphrase</span>
            <input
              v-model="oldPp"
              type="password"
              autocomplete="current-password"
              class="mt-1 w-full bg-slate-950 border border-slate-800 rounded-md
                     px-3 py-2 text-sm outline-none focus:border-accent"
            />
          </label>
          <label class="block">
            <span class="text-xs text-slate-400">New passphrase (min 8 chars)</span>
            <input
              v-model="newPp"
              type="password"
              autocomplete="new-password"
              class="mt-1 w-full bg-slate-950 border border-slate-800 rounded-md
                     px-3 py-2 text-sm outline-none focus:border-accent"
            />
          </label>
          <label class="block">
            <span class="text-xs text-slate-400">Confirm new passphrase</span>
            <input
              v-model="newPp2"
              type="password"
              autocomplete="new-password"
              class="mt-1 w-full bg-slate-950 border border-slate-800 rounded-md
                     px-3 py-2 text-sm outline-none focus:border-accent"
            />
          </label>
          <div class="flex justify-end gap-2">
            <button type="button" class="btn" :disabled="busy" @click="closeModal">Cancel</button>
            <button type="button" class="btn btn-accent" :disabled="busy" @click="submitPassphraseChange">
              Change passphrase
            </button>
          </div>
        </template>

        <!-- Delete passphrase -->
        <template v-else-if="modal === 'delete'">
          <h3 class="text-base font-semibold">Remove backup passphrase</h3>
          <p class="text-xs text-slate-400">
            Auto-backup will be disabled. Existing .zip files stay on disk
            and still need this passphrase to restore — removing it here
            does not break them, just forgets it on this app.
          </p>
          <label class="block">
            <span class="text-xs text-slate-400">Current passphrase</span>
            <input
              v-model="oldPp"
              type="password"
              autocomplete="current-password"
              class="mt-1 w-full bg-slate-950 border border-slate-800 rounded-md
                     px-3 py-2 text-sm outline-none focus:border-accent"
            />
          </label>
          <div class="flex justify-end gap-2">
            <button type="button" class="btn" :disabled="busy" @click="closeModal">Cancel</button>
            <button type="button" class="btn btn-accent" :disabled="busy" @click="submitPassphraseDelete">
              Remove passphrase
            </button>
          </div>
        </template>

        <!-- Restore -->
        <template v-else-if="modal === 'restore'">
          <h3 class="text-base font-semibold">Restore from backup</h3>
          <p class="text-xs text-slate-400">
            Pick a <code>.zip</code> backup file and enter the passphrase used
            when it was created. The restore is <strong>staged</strong>: nothing
            changes until you restart KeyLife. Your current DB will be saved
            as <code>.pre-restore.bak</code>.
          </p>
          <label class="block">
            <span class="text-xs text-slate-400">Backup file</span>
            <input
              type="file"
              accept=".zip,application/zip"
              @change="onFilePicked"
              class="mt-1 w-full text-xs text-slate-300
                     file:mr-3 file:px-3 file:py-1.5 file:rounded
                     file:border-0 file:bg-slate-800 file:text-slate-200
                     file:cursor-pointer"
            />
            <span v-if="restoreFile" class="text-[10px] text-slate-500 mt-1 block">
              {{ restoreFile.name }} · {{ fmtBytes(restoreFile.size) }}
            </span>
          </label>
          <label class="block">
            <span class="text-xs text-slate-400">Passphrase for this backup</span>
            <input
              v-model="restorePp"
              type="password"
              autocomplete="current-password"
              class="mt-1 w-full bg-slate-950 border border-slate-800 rounded-md
                     px-3 py-2 text-sm outline-none focus:border-accent"
            />
          </label>
          <div class="flex justify-end gap-2">
            <button type="button" class="btn" :disabled="busy" @click="closeModal">Cancel</button>
            <button type="button" class="btn btn-accent" :disabled="busy" @click="submitRestore">
              Stage restore
            </button>
          </div>
        </template>
      </div>
    </div>
  </section>
</template>
