const BASE = import.meta.env.VITE_API_URL || ''

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  })
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const body = await res.json()
      detail = body.detail || body.message || detail
    } catch {
      /* respuesta sin JSON */
    }
    throw new Error(detail)
  }
  if (res.status === 204) return null
  return res.json()
}

export const getStatus = () => request('/api/status')
export const getHealth = () => request('/api/health')
export const startBot = (mode, confirmReal = false) =>
  request('/api/bot/start', { method: 'POST', body: JSON.stringify({ mode, confirm_real: confirmReal }) })
export const stopBot = (closePositions = false) =>
  request('/api/bot/stop', { method: 'POST', body: JSON.stringify({ close_positions: closePositions }) })
export const panic = () => request('/api/bot/panic', { method: 'POST' })

export const getCandles = (timeframe = 'M5', limit = 240) =>
  request(`/api/candles?timeframe=${timeframe}&limit=${limit}`)
export const getSymbol = () => request('/api/symbols/btc')
export const rescanSymbol = () => request('/api/symbols/rescan', { method: 'POST' })

export const getTrades = (params = {}) => {
  const qs = new URLSearchParams({ limit: 200, ...params }).toString()
  return request(`/api/trades?${qs}`)
}
export const getMetrics = (mode) => request(`/api/metrics${mode ? `?mode=${mode}` : ''}`)

export const getConfig = () => request('/api/config')
export const patchConfig = (patch) => request('/api/config', { method: 'PATCH', body: JSON.stringify(patch) })

export const runBacktest = (payload) => request('/api/backtest', { method: 'POST', body: JSON.stringify(payload) })
export const listBacktests = () => request('/api/backtests')
export const getBacktest = (id) => request(`/api/backtests/${id}`)

export const mlStatus = () => request('/api/ml/status')
export const trainMl = (payload) => request('/api/ml/train', { method: 'POST', body: JSON.stringify(payload) })
