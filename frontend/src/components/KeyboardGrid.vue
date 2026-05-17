<script setup lang="ts">
import { computed } from 'vue'
import type { KeyboardLayout, LayoutKey } from '../types'

const props = withDefaults(defineProps<{
  layout: KeyboardLayout
  unitPx?: number
  gapPx?: number
}>(), {
  unitPx: 48,
  gapPx: 4,
})

const widthPx  = computed(() => props.layout.width  * props.unitPx)
const heightPx = computed(() => props.layout.height * props.unitPx)

function styleFor(k: LayoutKey) {
  return {
    left:   (k.x * props.unitPx + props.gapPx / 2) + 'px',
    top:    (k.y * props.unitPx + props.gapPx / 2) + 'px',
    width:  ((k.w ?? 1) * props.unitPx - props.gapPx) + 'px',
    height: ((k.h ?? 1) * props.unitPx - props.gapPx) + 'px',
  }
}
</script>

<template>
  <div
    class="relative mx-auto"
    :style="{ width: widthPx + 'px', height: heightPx + 'px' }"
  >
    <template v-for="k in layout.keys" :key="k.id">
      <slot name="cell" :keyDef="k" :style="styleFor(k)">
        <div
          class="absolute rounded-md border border-slate-700/50 bg-slate-900
                 flex items-center justify-center text-xs text-slate-300"
          :style="styleFor(k)"
        >
          {{ k.label }}
        </div>
      </slot>
    </template>
  </div>
</template>
