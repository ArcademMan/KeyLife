<script setup lang="ts">
defineProps<{
  label: string
  value: string | number
  hint?: string
  accent?: boolean
}>()

function fmt(v: string | number) {
  if (typeof v === 'number') return v.toLocaleString()
  return v
}
</script>

<template>
  <div class="panel panel-pad" :class="accent ? 'ring-1 ring-accent/40' : ''">
    <div class="panel-title">{{ label }}</div>
    <div class="mt-2 text-3xl font-bold tracking-tight tabular-nums">
      {{ fmt(value) }}
    </div>
    <div v-if="hint" class="mt-1 text-xs text-slate-400">{{ hint }}</div>
  </div>
</template>
