<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
import type { KeyboardLayout } from '../types'
import SettingsTabs from '../components/settings/SettingsTabs.vue'
import HandMappingSection from '../components/settings/HandMappingSection.vue'
import PerAppSection from '../components/settings/PerAppSection.vue'
import BackupsSection from '../components/settings/BackupsSection.vue'
import { usePersistedRef } from '../lib/storage'

const layout = ref<KeyboardLayout | null>(null)
const error = ref<string | null>(null)

// Persisti il tab attivo: navigando via e tornando, l'utente si ritrova
// dove era. localStorage ok, è solo una preferenza UI.
const activeTab = usePersistedRef<string>('keylife.settings.tab.v1', 'handmap')

const TABS = [
  { id: 'handmap', label: 'Hand mapping' },
  { id: 'perapp',  label: 'Per-app tracking' },
  { id: 'backups', label: 'Backups' },
]

onMounted(async () => {
  try {
    layout.value = await api.layout()
  } catch (e: any) {
    error.value = e?.message ?? 'failed to load layout'
  }
})
</script>

<template>
  <div v-if="error" class="panel panel-pad text-red-300" role="alert">
    {{ error }}
  </div>

  <div v-else>
    <SettingsTabs v-model="activeTab" :tabs="TABS" />

    <HandMappingSection v-if="activeTab === 'handmap'" :layout="layout" />
    <PerAppSection v-else-if="activeTab === 'perapp'" />
    <BackupsSection v-else-if="activeTab === 'backups'" />
  </div>
</template>
