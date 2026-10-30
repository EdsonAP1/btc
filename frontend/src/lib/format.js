export const money = (value, digits = 2) => {
  const n = Number(value)
  if (!Number.isFinite(n)) return '—'
  return n.toLocaleString('es-AR', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

export const usd = (value, digits = 2) => `${Number(value) >= 0 ? '' : '-'}$${money(Math.abs(Number(value)), digits)}`

export const signedUsd = (value, digits = 2) => {
  const n = Number(value)
  if (!Number.isFinite(n)) return '—'
  return `${n >= 0 ? '+' : '-'}$${money(Math.abs(n), digits)}`
}

export const pct = (value, digits = 1) => {
  const n = Number(value)
  if (!Number.isFinite(n)) return '—'
  return `${n.toFixed(digits)}%`
}

export const signedPct = (value, digits = 2) => {
  const n = Number(value)
  if (!Number.isFinite(n)) return '—'
  return `${n >= 0 ? '+' : ''}${n.toFixed(digits)}%`
}

export const num = (value, digits = 2) => {
  const n = Number(value)
  if (!Number.isFinite(n)) return '—'
  return n.toFixed(digits)
}

export const price = (value, digits = 2) => {
  const n = Number(value)
  if (!Number.isFinite(n) || n === 0) return '—'
  return money(n, digits)
}

export const timeShort = (iso) => {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return String(iso).slice(11, 19)
  return d.toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

export const dateTime = (iso) => {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return String(iso)
  return d.toLocaleString('es-AR', {
    day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
  })
}

export const duration = (seconds) => {
  const s = Math.max(0, Math.floor(Number(seconds) || 0))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  if (h) return `${h}h ${m}m`
  if (m) return `${m}m ${sec}s`
  return `${sec}s`
}

export const tone = (value) => (Number(value) > 0 ? 'pos' : Number(value) < 0 ? 'neg' : 'muted')
