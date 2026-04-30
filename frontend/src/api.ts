import axios from 'axios'
import type {
  AppsHourly,
  AppsSummary,
  ForgetAppResult,
  HourlyHeatmap,
  KeyboardHeatmap,
  KeyboardLayout,
  PerAppSettings,
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

  // Per-app tracking
  perAppSettings: () =>
    http.get<PerAppSettings>('/settings/per-app').then(r => r.data),

  setPerAppSettings: (patch: Partial<PerAppSettings>) =>
    http.put<PerAppSettings>('/settings/per-app', patch).then(r => r.data),

  appsSummary: (range: DateRange & { limit?: number } = {}) =>
    http.get<AppsSummary>('/apps/summary', { params: range }).then(r => r.data),

  appsHourly: (range: DateRange & { exe_name?: string } = {}) =>
    http.get<AppsHourly>('/apps/hourly', { params: range }).then(r => r.data),

  forgetApp: (exe_name: string) =>
    http.post<ForgetAppResult>('/apps/forget', { exe_name }).then(r => r.data),

  // Costruisci la URL dell'icona — non un GET diretto: il browser la
  // userà come <img src=...> sfruttando la cache HTTP (ETag).
  appIconUrl: (exe_name: string) =>
    `/api/app-icons/${encodeURIComponent(exe_name)}`,
}
