<script setup lang="ts">
import { computed } from 'vue'
import type { KeyCount } from '../../types'
import {
  categorize, CATEGORY_COLORS, CATEGORY_ORDER, type Category,
} from '../../lib/vk'
import { TOOLTIP } from '../../lib/chartTheme'
import ChartBox from '../ChartBox.vue'

const props = defineProps<{ keys: KeyCount[] }>()

interface Bucket { name: Category; value: number }

const buckets = computed<Bucket[]>(() => {
  const sums = new Map<Category, number>()
  for (const k of props.keys) {
    const cat = categorize(k.vk)
    sums.set(cat, (sums.get(cat) ?? 0) + k.count)
  }
  return CATEGORY_ORDER
    .map(c => ({ name: c, value: sums.get(c) ?? 0 }))
    .filter(b => b.value > 0)
})

const option = computed(() => ({
  backgroundColor: 'transparent',
  tooltip: {
    trigger: 'item',
    ...TOOLTIP,
    formatter: (p: any) =>
      `${p.name}<br><b>${p.value.toLocaleString()}</b> presses · ${p.percent}%`,
  },
  legend: {
    orient: 'vertical',
    right: 8, top: 'middle',
    textStyle: { color: '#cbd5e1', fontSize: 11 },
    itemWidth: 10, itemHeight: 10,
  },
  series: [{
    type: 'pie',
    radius: ['50%', '78%'],
    center: ['35%', '50%'],
    avoidLabelOverlap: true,
    itemStyle: { borderColor: '#0f172a', borderWidth: 2 },
    label: { show: false },
    labelLine: { show: false },
    data: buckets.value.map(b => ({
      ...b,
      itemStyle: { color: CATEGORY_COLORS[b.name] },
    })),
  }],
}))
</script>

<template>
  <div class="panel panel-pad lg:col-span-1">
    <div class="panel-title mb-3">By category</div>
    <ChartBox :option="option" height="240px" />
  </div>
</template>
