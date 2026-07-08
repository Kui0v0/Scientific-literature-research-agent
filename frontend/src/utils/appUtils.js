export function readJsonStorage(key, fallback) {
  if (typeof localStorage === 'undefined') return fallback
  try {
    const raw = localStorage.getItem(key)
    return raw ? JSON.parse(raw) : fallback
  } catch {
    return fallback
  }
}

export function writeJsonStorage(key, value) {
  if (typeof localStorage === 'undefined') return
  localStorage.setItem(key, JSON.stringify(value))
}

export function emptyGapStats() {
  return {
    is_real: true,
    query: '',
    record_count: 0,
    field_record_count: 0,
    research_area: null,
    metrics: [],
    current_values: [],
    average_values: [],
  }
}

export function normalizeUserStats(stats = {}) {
  return {
    literature: Number(stats.literature || 0),
    summaries: Number(stats.summaries || 0),
    experiments: Number(stats.experiments || 0),
    reports: Number(stats.reports || 0),
  }
}

export function formatNumber(value) {
  return Number(value).toLocaleString('en-US')
}

export function progressValue(value, max) {
  return Math.max(8, Math.round((value / max) * 100))
}

export function radarAxis(index, radius = 96) {
  const angle = -Math.PI / 2 + (index * Math.PI * 2) / 6
  return {
    x: 150 + Math.cos(angle) * radius,
    y: 136 + Math.sin(angle) * radius,
  }
}

export function radarLabelPosition(index) {
  return [
    { x: 150, y: 22, anchor: 'middle' },
    { x: 236, y: 86, anchor: 'start' },
    { x: 226, y: 204, anchor: 'start' },
    { x: 150, y: 263, anchor: 'middle' },
    { x: 70, y: 204, anchor: 'end' },
    { x: 64, y: 86, anchor: 'end' },
  ][index] || { x: 150, y: 136, anchor: 'middle' }
}

export function radarGrid(scale) {
  return Array.from({ length: 6 }, (_, index) => radarAxis(index, 96 * scale))
    .map((point) => `${point.x},${point.y}`)
    .join(' ')
}

export function radarPoints(values) {
  return values.map((value, index) => radarAxis(index, value * 0.96))
}

export function radarPolygon(values) {
  return radarPoints(values)
    .map((point) => `${point.x},${point.y}`)
    .join(' ')
}

export function normalizeReportFormat(format) {
  const value = String(format || '').toLowerCase()
  if (value === 'pdf') return 'pdf'
  if (value === 'word' || value === 'docx') return 'docx'
  return 'markdown'
}
