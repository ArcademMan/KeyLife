import axios from 'axios'
import type {
  AppsHourly,
  AppsSummary,
  BackupConfig,
  BackupConfigPatch,
  BackupInfo,
  ForgetAppResult,
  HourlyHeatmap,
  KeyboardHeatmap,
  KeyboardLayout,
  PerAppSettings,
  RestoreStaged,
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

  // --- Backup -----------------------------------------------------------
  backupConfig: () => http.get<BackupConfig>('/settings/backup').then(r => r.data),

  setBackupConfig: (patch: BackupConfigPatch) =>
    http.put<BackupConfig>('/settings/backup', patch).then(r => r.data),

  setBackupPassphrase: (new_passphrase: string, old_passphrase?: string) =>
    http.put<BackupConfig>('/settings/backup/passphrase', {
      new_passphrase, old_passphrase: old_passphrase ?? null,
    }).then(r => r.data),

  deleteBackupPassphrase: (passphrase: string) =>
    // axios DELETE non manda body di default — passalo via `data`.
    http.delete<BackupConfig>('/settings/backup/passphrase', {
      data: { passphrase },
    }).then(r => r.data),

  listBackups: () => http.get<BackupInfo[]>('/backups').then(r => r.data),

  backupNow: () => http.post<BackupInfo>('/backups/now').then(r => r.data),

  deleteBackup: (filename: string) =>
    http.delete<void>(`/backups/${encodeURIComponent(filename)}`).then(r => r.data),

  restoreFromZip: (file: File, passphrase: string) => {
    // Upload più grande del default axios JSON timeout (10s): un .zip da
    // 50 MB + scrypt unwrap richiede di più. 60s è ampiamente sufficiente.
    const form = new FormData()
    form.append('file', file)
    form.append('passphrase', passphrase)
    return http.post<RestoreStaged>('/backups/restore', form, {
      timeout: 60_000,
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then(r => r.data)
  },

  cancelRestore: () => http.delete<void>('/backups/restore').then(r => r.data),
}
