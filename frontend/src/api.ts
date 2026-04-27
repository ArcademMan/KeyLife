import axios from 'axios'
import type {
  HourlyHeatmap,
  KeyboardHeatmap,
  KeyboardLayout,
  Summary,
  Timeline,
  TopKeys,
} from './types'

const http = axios.create({ baseURL: '/api', timeout: 10000 })

export interface DateRange {
  start?: string
  end?: string
}

export const api = {
  summary: () => http.get<Summary>('/stats/summary').then(r => r.data),

  top: (range: DateRange & { limit?: number } = {}) =>
    http.get<TopKeys>('/stats/top', { params: range }).then(r => r.data),

  timeline: (range: DateRange = {}) =>
    http.get<Timeline>('/timeline/daily', { params: range }).then(r => r.data),

  hourly: (range: DateRange = {}) =>
    http.get<HourlyHeatmap>('/heatmap/hourly', { params: range }).then(r => r.data),

  keyboard: (range: DateRange = {}) =>
    http.get<KeyboardHeatmap>('/heatmap/keyboard', { params: range }).then(r => r.data),

  layout: () => http.get<KeyboardLayout>('/keyboard/layout').then(r => r.data),
}
