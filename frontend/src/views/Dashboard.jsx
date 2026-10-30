import { useEffect, useMemo, useState } from 'react'
import { getCandles, getMetrics, getTrades } from '../api.js'
import CandleChart from '../components/CandleChart.jsx'
import EquityChart from '../components/EquityChart.jsx'
import LogsPanel from '../components/LogsPanel.jsx'
import PositionsTable from '../components/PositionsTable.jsx'
import StatCard from '../components/StatCard.jsx'
import TradesTable from '../components/TradesTable.jsx'
import { duration, money, pct, price, signedUsd, tone } from '../lib/format.js'

export default function Dashboard({ status }) {
  const [candles, setCandles] = useState([])
  const [metrics, setMetrics] = useState(null)
  const [trades, setTrades] = useState([])

  const timeframe = status?.bot?.timeframe || 'M15'
  const botState = status?.bot?.state || 'stopped'
  const metricsMode =
    status?.bot?.mode === 'paper' || status?.bot?.mode === 'sim' ? status.bot.mode : 'live'

  useEffect(() => {
    let alive = true
    const load = async () => {
      try {
        const data = await getCandles(timeframe, 220)
        if (alive) setCandles(data.candles || [])
      } catch {
        /* sin datos */
      }
    }
    load()
    const interval = setInterval(load, 20000)
    return () => {
      alive = false
      clearInterval(interval)
    }
  }, [timeframe])

  useEffect(() => {
    let alive = true
    const load = async () => {
      try {
        const [m, t] = await Promise.all([
          getMetrics(metricsMode),
          getTrades({ limit: 12, mode: metricsMode }),
        ])
        if (alive) {
          setMetrics(m)
          setTrades(t.items || [])
        }
      } catch {
        /* sin datos */
      }
    }
    load()
    const interval = setInterval(load, 15000)
    return () => {
      alive = false
      clearInterval(interval)
    }
  }, [botState, metricsMode])

  const account = status?.account || {}
  const today = status?.today || {}
  const risk = status?.risk || {}
  const positions = status?.positions || []
  const market = status?.market || {}
  const bot = status?.bot || {}

  const equity = Number(account.equity ?? risk.equity ?? 0)
  const balance = Number(account.balance ?? 0)
  const floating = Number(account.profit ?? equity - balance)

  const equityCurve = useMemo(() => {
    const curve = metrics?.equity_curve || []
    if (!curve.length) return []
    return curve.map((point) => ({ ...point, time: point.time }))
  }, [metrics])

  const lastSignal = bot.last_signal
  const signalLabel =
    lastSignal?.action === 'buy' ? 'Compra' : lastSignal?.action === 'sell' ? 'Venta' : 'Sin señal'
  const equityLabel =
    botState === 'running'
      ? bot.mode === 'live'
        ? 'Equity (cuenta MT5)'
        : 'Equity paper'
      : 'Equity (MT5)'

  return (
    <div className="stack">
      {!status ? (
        <div className="banner info">Conectando con el backend…</div>
      ) : null}

      {status && !status.mt5?.connected ? (
        <div className="banner">
          MT5 no está conectado. El panel muestra datos simulados; abrí el terminal y volvé a iniciar el bot
          para operar en real.
        </div>
      ) : null}

      <div className="grid stats">
        <StatCard
          label={equityLabel}
          value={`$${money(equity, 2)}`}
          sub={`Balance $${money(balance, 2)} · flotante ${signedUsd(floating)}`}
        />
        <StatCard
          label="P&L de hoy"
          value={signedUsd(today.pnl ?? 0)}
          tone={tone(today.pnl)}
          sub={`${today.trades ?? 0} operaciones cerradas`}
        />
        <StatCard
          label="Winrate de hoy"
          value={pct(today.winrate ?? 0, 1)}
          sub={`Histórico: ${pct(metrics?.winrate ?? 0, 1)} en ${metrics?.trades ?? 0} trades`}
        />
        <StatCard
          label="Posiciones"
          value={`${positions.length} / ${risk.max_positions ?? 1}`}
          sub={`Riesgo ${risk.risk_pct ?? 1}% · ${risk.trades_today ?? 0}/${risk.max_trades_per_day ?? '∞'} trades hoy`}
        />
        <StatCard
          label="Drawdown"
          value={pct(risk.drawdown_pct ?? 0, 2)}
          tone={Number(risk.drawdown_pct) >= Number(risk.max_drawdown_pct || 100) * 0.8 ? 'neg' : ''}
          sub={`Pico $${money(risk.peak_equity ?? 0, 0)} · límite ${pct(risk.max_drawdown_pct ?? 0, 0)}`}
        />
        <StatCard
          label="Última señal"
          value={signalLabel}
          tone={lastSignal?.action === 'buy' ? 'pos' : lastSignal?.action === 'sell' ? 'neg' : ''}
          sub={lastSignal?.reason || `Timeframe ${timeframe}`}
        />
      </div>

      <div className="grid two">
        <div className="card">
          <div className="card-head">
            <div>
              <div className="card-title">{status?.symbol?.name || 'BTC'} · {timeframe}</div>
              <div className="card-hint">
                Spread {market.spread_points ?? '—'} pts · actualizado {market.time ? market.time.slice(11, 19) : '—'} UTC
              </div>
            </div>
            <div className="price-block">
              <span className="price num">{price(market.bid, 2)}</span>
              <span className="price-symbol">bid</span>
            </div>
          </div>
          <CandleChart candles={candles} height={265} />
        </div>

        <div className="card">
          <div className="card-head">
            <div className="card-title">Curva de equity</div>
            <div className="card-hint">
              {metrics ? `${signedUsd(metrics.net_pnl)} · DD ${pct(metrics.max_drawdown_pct, 1)}` : '—'}
            </div>
          </div>
          <EquityChart data={equityCurve} height={265} color={Number(metrics?.net_pnl) >= 0 ? '#16c784' : '#ea3943'} />
        </div>
      </div>

      <div className="grid two">
        <div className="card">
          <div className="card-head">
            <div className="card-title">Posiciones abiertas</div>
            <div className="card-hint">{positions.length ? signedUsd(positions.reduce((acc, p) => acc + Number(p.profit || 0), 0)) : 'sin exposición'}</div>
          </div>
          <PositionsTable positions={positions} />
        </div>

        <div className="card">
          <div className="card-head">
            <div className="card-title">Actividad</div>
            <div className="card-hint">
              {botState === 'running' ? `activo hace ${duration(bot.uptime_sec)}` : 'bot detenido'}
            </div>
          </div>
          <LogsPanel logs={status?.logs || []} />
        </div>
      </div>

      <div className="card">
        <div className="card-head">
          <div className="card-title">Últimas operaciones</div>
          <div className="card-hint">Historial completo en la pestaña Operaciones</div>
        </div>
        <TradesTable trades={trades} limit={10} />
      </div>
    </div>
  )
}
