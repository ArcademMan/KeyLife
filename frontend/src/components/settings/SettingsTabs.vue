<script setup lang="ts">
import { computed } from 'vue'

interface Tab {
  id: string
  label: string
}

const props = defineProps<{
  tabs: Tab[]
  modelValue: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', id: string): void
}>()

const active = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

function pick(id: string) { active.value = id }
</script>

<template>
  <div
    class="flex items-center gap-1 border-b border-slate-800 mb-6 overflow-x-auto"
    role="tablist"
  >
    <button
      v-for="t in tabs"
      :key="t.id"
      type="button"
      role="tab"
      :aria-selected="active === t.id"
      class="px-4 py-2.5 text-sm font-medium transition-colors border-b-2
             -mb-px whitespace-nowrap focus-visible:outline-none
             focus-visible:ring-2 focus-visible:ring-accent/50 rounded-t-md"
      :class="active === t.id
        ? 'border-accent text-white'
        : 'border-transparent text-slate-400 hover:text-slate-200 hover:border-slate-700'"
      @click="pick(t.id)"
    >
      {{ t.label }}
    </button>
  </div>
</template>
