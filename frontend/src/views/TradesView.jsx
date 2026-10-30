import { useEffect, useState } from 'react'
import { getMetrics, getTrades } from '../api.js'
import MetricGrid from '../components/MetricGrid.jsx'
import TradesTable from '../components/TradesTable.jsx'
import EquityChart from '../components/EquityChart.jsx'
import { num, pct, signedUsd } from '../lib/format.js'

const FILTERS = [
  { key: '', label: 'Todas' },
  { key: 'closed', label: 'Cerradas' },
  { key: 'open', label: 'Abiertas' },
]

const MODES = [
  { key: 'live', label: 'Cuenta MT5' },
  { key: 'paper', label: 'Paper' },
  { key: '', label: 'Todos los modos' },
]

export default function TradesView() {
  const [trades, setTrades] = useState([])
  const [metrics, setMetrics] = useState(null)
  const [filter, setFilter] = useState('')
  const [modeFilter, setModeFilter] = useState('live')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const load = async () => {
    setLoading(true)
    try {
      const [t, m] = await Promise.all([
        getTrades({ limit: 300, mode: modeFilter, ...(filter ? { status: filter } : {}) }),
        getMetrics(modeFilter),
      ])
      setTrades(t.items || [])
      setMetrics(m)
      setError(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [filter, modeFilter])

  const byHour = metrics?.by_hour || []
  const bestHour = byHour.length ? byHour.reduce((a, b) => (b.pnl > a.pnl ? b : a)) : null

  return (
    <div className="stack">
      {error ? <div className="banner">{error}</div> : null}

      <MetricGrid metrics={metrics} />

      <div className="grid two">
        <div className="card">
          <div className="card-head">
            <div className="card-title">Equity acumulada</div>
            <div className="card-hint">{metrics ? `${metrics.trades} operaciones cerradas` : ''}</div>
          </div>
          <EquityChart
            data={metrics?.equity_curve || []}
            height={230}
            color={(metrics?.net_pnl ?? 0) >= 0 ? '#16c784' : '#ea3943'}
          />
        </div>

        <div className="card">
          <div className="card-head">
            <div className="card-title">Rendimiento por hora</div>
            <div className="card-hint">{bestHour ? `mejor: ${bestHour.hour}:00 (${signedUsd(bestHour.pnl)})` : '—'}</div>
          </div>
          <div className="table-wrap" style={{ maxHeight: 230 }}>
            <table>
              <thead>
                <tr>
                  <th>Hora</th>
                  <th>Trades</th>
                  <th>Winrate</th>
                  <th>P&amp;L</th>
                </tr>
              </thead>
              <tbody>
                {byHour.length ? (
                  byHour.map((row) => (
                    <tr key={row.hour}>
                      <td className="num">{String(row.hour).padStart(2, '0')}:00</td>
                      <td className="num">{row.trades}</td>
                      <td className="num">{pct(row.winrate, 1)}</td>
                      <td className={`num ${row.pnl >= 0 ? 'pos' : 'neg'}`}>{signedUsd(row.pnl)}</td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={4} className="empty">Sin datos suficientes.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-head">
          <div className="card-title">Historial de operaciones</div>
          <div className="row wrap">
            {MODES.map((item) => (
              <button
                key={item.key || 'all'}
                className={`btn sm ${modeFilter === item.key ? 'primary' : 'ghost'}`}
                onClick={() => setModeFilter(item.key)}
              >
                {item.label}
              </button>
            ))}
            <span style={{ width: 8 }} />
            {FILTERS.map((item) => (
              <button
                key={item.key}
                className={`btn sm ${filter === item.key ? 'primary' : 'ghost'}`}
                onClick={() => setFilter(item.key)}
              >
                {item.label}
              </button>
            ))}
            <button className="btn sm" onClick={load} disabled={loading}>
              {loading ? 'Actualizando…' : 'Actualizar'}
            </button>
          </div>
        </div>
        <TradesTable trades={trades} empty={loading ? 'Cargando…' : 'No hay operaciones con ese filtro.'} />
        <div className="card-hint" style={{ marginTop: 10 }}>
          Mostrando {trades.length} registros · P&L acumulado {signedUsd(metrics?.net_pnl ?? 0)} · expectancy {signedUsd(metrics?.expectancy ?? 0)} · avg R {num(metrics?.avg_r ?? 0, 2)}
        </div>
      </div>
    </div>
  )
}
