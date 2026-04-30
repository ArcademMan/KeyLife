import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import {
  BarChart, LineChart, HeatmapChart, ScatterChart, PieChart,
} from 'echarts/charts'
import {
  GridComponent, TooltipComponent, TitleComponent,
  VisualMapComponent, CalendarComponent, DataZoomComponent,
  LegendComponent,
} from 'echarts/components'

import App from './App.vue'
import { router } from './router'
import { attachNavProgress } from './nav-progress'
import './style.css'

attachNavProgress(router)

use([
  CanvasRenderer,
  BarChart, LineChart, HeatmapChart, ScatterChart, PieChart,
  GridComponent, TooltipComponent, TitleComponent,
  VisualMapComponent, CalendarComponent, DataZoomComponent,
  LegendComponent,
])

createApp(App)
  .use(createPinia())
  .use(router)
  .mount('#app')
