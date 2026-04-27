<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, watch, shallowRef } from 'vue'
import { init, type EChartsType, type EChartsCoreOption } from 'echarts/core'

const props = defineProps<{
  option: EChartsCoreOption
  height?: string
}>()

const emit = defineEmits<{
  (e: 'chart-click', params: any): void
}>()

const root = ref<HTMLDivElement | null>(null)
const chart = shallowRef<EChartsType | null>(null)

function resize() { chart.value?.resize() }

onMounted(() => {
  if (!root.value) return
  chart.value = init(root.value, 'dark', { renderer: 'canvas' })
  chart.value.setOption(props.option)
  chart.value.on('click', (p: any) => emit('chart-click', p))
  window.addEventListener('resize', resize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', resize)
  chart.value?.dispose()
})

watch(() => props.option, (opt) => {
  chart.value?.setOption(opt, true)
}, { deep: true })
</script>

<template>
  <div ref="root" :style="{ width: '100%', height: height || '320px', background: 'transparent' }" />
</template>
