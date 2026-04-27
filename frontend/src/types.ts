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
