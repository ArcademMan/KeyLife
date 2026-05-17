export interface KeyCount {
  vk: number
  scancode: number
  name: string
  count: number
}

export interface Summary {
  today: string
  today_total: number
  session_total: number
  all_time_total: number
  first_recorded_date: string | null
  flush_interval_seconds: number
}

export interface DailyTotal {
  date: string
  total: number
}

export interface Timeline {
  start: string
  end: string
  days: DailyTotal[]
}

export interface HourlyCell {
  date: string
  hour: number
  total: number
}

export interface HourlyHeatmap {
  start: string
  end: string
  cells: HourlyCell[]
}

export interface TopKeys {
  start: string
  end: string
  keys: KeyCount[]
}

export interface KeyboardHeatmap {
  start: string
  end: string
  keys: KeyCount[]
}

export interface LayoutKey {
  id: string
  label: string
  x: number
  y: number
  w?: number
  h?: number
  vk?: number
  scancode?: number
}

export interface KeyboardLayout {
  name: string
  unit: string
  width: number
  height: number
  notes?: string
  keys: LayoutKey[]
}

// --- Per-app tracking ---------------------------------------------------

export interface PerAppSettings {
  tracking_enabled: boolean
  blocklist: string[]
}

export interface AppCount {
  exe_name: string
  count: number
  has_icon: boolean
}

export interface AppsSummary {
  start: string
  end: string
  apps: AppCount[]
}

export interface AppHourlyCell {
  date: string
  hour: number
  exe_name: string
  count: number
}

export interface AppsHourly {
  start: string
  end: string
  cells: AppHourlyCell[]
}

export interface ForgetAppResult {
  exe_name: string
  rows_deleted: number
}

// --- Backup -------------------------------------------------------------

export interface BackupConfig {
  enabled: boolean
  interval_hours: number
  keep_n: number
  dir: string | null
  resolved_dir: string
  has_passphrase: boolean
  last_backup_at: string | null
  restore_pending: boolean
}

export interface BackupConfigPatch {
  enabled?: boolean
  interval_hours?: number
  keep_n?: number
  // `null` o `""` → reset al default. Omettere → invariato.
  dir?: string | null
}

export interface BackupInfo {
  filename: string
  size: number
  created_at: string
}

export interface RestoreStaged {
  staged_at: string
  source_filename: string
  restart_required: boolean
}
