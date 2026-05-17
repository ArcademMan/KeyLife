<script setup lang="ts">
import { api } from '../api'

withDefaults(defineProps<{
  exe: string
  hasIcon?: boolean
  size?: number
}>(), {
  hasIcon: true,
  size: 32,
})

// Inline SVG placeholder shown when the backend has no icon for an exe
// (UWP host, anti-cheat-protected process, extraction failed). Inlined as
// a data URI so we don't fire a network request for the fallback.
const FALLBACK = (() => {
  const svg = `<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'>
    <rect x='2' y='2' width='28' height='28' rx='6' fill='%23334155'/>
    <text x='16' y='22' font-family='ui-sans-serif' font-size='14'
          fill='%23cbd5e1' text-anchor='middle'>?</text>
  </svg>`
  return `data:image/svg+xml;utf8,${svg.replace(/\s+/g, ' ').trim()}`
})()

function onError(e: Event): void {
  const img = e.target as HTMLImageElement
  if (img.src !== FALLBACK) img.src = FALLBACK
}
</script>

<template>
  <img
    :src="hasIcon ? api.appIconUrl(exe) : FALLBACK"
    :alt="''"
    :width="size"
    :height="size"
    class="shrink-0 rounded-sm bg-slate-900 object-contain"
    :style="{ width: size + 'px', height: size + 'px' }"
    loading="lazy"
    decoding="async"
    @error="onError"
  />
</template>
