// Shared ECharts styling tokens. Each view used to inline the same dark
// tooltip background, axis colors, and heatmap gradient — centralize so
// a palette tweak is one edit, not seven.

export const COLORS = {
  accent: '#7c5cff',
  accentSoft: '#5e44d6',
  bgTooltip: '#0f172a',
  borderTooltip: '#334155',
  textTooltip: '#e2e8f0',
  axisLine: '#334155',
  axisLabel: '#cbd5e1',
  axisLabelDim: '#94a3b8',
  splitLine: '#1e293b',
  heatmapBorder: '#020617',
} as const

export const TOOLTIP = {
  backgroundColor: COLORS.bgTooltip,
  borderColor: COLORS.borderTooltip,
  textStyle: { color: COLORS.textTooltip },
}

// Visual map color stops used by calendar + hourly + weekday heatmaps.
export const HEATMAP_RANGE: readonly string[] = [
  '#1e293b', '#3b3170', '#5b46c4', '#7c5cff', '#b39dff',
]

export const AXIS_VALUE = {
  axisLine: { show: false },
  axisTick: { show: false },
  splitLine: { lineStyle: { color: COLORS.splitLine } },
  axisLabel: { color: COLORS.axisLabelDim },
}

export const AXIS_CATEGORY = {
  axisLine: { lineStyle: { color: COLORS.axisLine } },
  axisLabel: { color: COLORS.axisLabel, fontSize: 11 },
}

export function visualMap(max: number, extra: Record<string, unknown> = {}) {
  return {
    min: 0,
    max: Math.max(1, max),
    orient: 'horizontal' as const,
    left: 'center',
    bottom: 10,
    inRange: { color: [...HEATMAP_RANGE] },
    textStyle: { color: COLORS.axisLabel },
    ...extra,
  }
}
