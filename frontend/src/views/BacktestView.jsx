import { useEffect, useState } from 'react'
import { getConfig, listBacktests, getBacktest, runBacktest } from '../api.js'
import EquityChart from '../components/EquityChart.jsx'
import MetricGrid from '../components/MetricGrid.jsx'
import TradesTable from '../components/TradesTable.jsx'
import { dateTime, num, signedUsd } from '../lib/format.js'

const TIMEFRAMES = ['M1', 'M5', 'M15', 'M30', 'H1', 'H4', 'D1']

const EMPTY_FORM = {
  timeframe: 'M5',
  bars: 5000,
  risk_pct: 1,
  spread_points: '',
  commission_per_lot: 0,
  ema_fast: 21,
  ema_slow: 55,
  rsi_long_max: 72,
  rsi_short_min: 28,
  sl_atr: 1.6,
  tp_atr: 2.6,
  cooldown_bars: 2,
}

export default function BacktestView() {
  const [form, setForm] = useState(EMPTY_FORM)
  const [result, setResult] = useState(null)
  const [history, setHistory] = useState([])
  const [running, setRunning] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    getConfig()
      .then((cfg) => {
        setForm((prev) => ({
          ...prev,
          timeframe: cfg.timeframe || prev.timeframe,
          bars: cfg.backtest?.bars ?? prev.bars,
          risk_pct: cfg.backtest?.risk_pct ?? prev.risk_pct,
          commission_per_lot: cfg.backtest?.commission_per_lot ?? 0,
          ema_fast: cfg.strategy?.ema_fast ?? prev.ema_fast,
          ema_slow: cfg.strategy?.ema_slow ?? prev.ema_slow,
          rsi_long_max: cfg.strategy?.rsi_long_max ?? prev.rsi_long_max,
          rsi_short_min: cfg.strategy?.rsi_short_min ?? prev.rsi_short_min,
          sl_atr: cfg.strategy?.sl_atr ?? prev.sl_atr,
          tp_atr: cfg.strategy?.tp_atr ?? prev.tp_atr,
          cooldown_bars: cfg.strategy?.cooldown_bars ?? prev.cooldown_bars,
        }))
      })
      .catch(() => {})
    refreshHistory()
  }, [])

  const refreshHistory = async () => {
    try {
      const data = await listBacktests()
      setHistory(data.items || [])
    } catch {
      /* sin historial */
    }
  }

  const update = (key, value) => setForm((prev) => ({ ...prev, [key]: value }))

  const execute = async () => {
    setRunning(true)
    setError(null)
    try {
      const payload = {
        timeframe: form.timeframe,
        bars: Number(form.bars),
        risk_pct: Number(form.risk_pct),
        commission_per_lot: Number(form.commission_per_lot || 0),
        spread_points: form.spread_points === '' ? null : Number(form.spread_points),
        params: {
          ema_fast: Number(form.ema_fast),
          ema_slow: Number(form.ema_slow),
          rsi_long_max: Number(form.rsi_long_max),
          rsi_short_min: Number(form.rsi_short_min),
          sl_atr: Number(form.sl_atr),
          tp_atr: Number(form.tp_atr),
          cooldown_bars: Number(form.cooldown_bars),
        },
      }
      const data = await runBacktest(payload)
      setResult(data)
      refreshHistory()
    } catch (err) {
      setError(err.message)
    } finally {
      setRunning(false)
    }
  }

  const loadRun = async (id) => {
    try {
      const run = await getBacktest(id)
      setResult({
        run_id: run.id,
        metrics: run.metrics,
        params: run.params,
        trades: run.trades,
        equity_curve: run.equity_curve,
      })
    } catch (err) {
      setError(err.message)
    }
  }

  const metrics = result?.metrics

  return (
    <div className="stack">
      {error ? <div className="banner">{error}</div> : null}

      <div className="grid two">
        <div className="card">
          <div className="card-head">
            <div>
              <div className="card-title">Configurar backtest</div>
              <div className="card-hint">Mismas reglas que el bot en vivo · spread real de las velas si lo dejás vacío</div>
            </div>
          </div>

          <div className="form-grid">
            <div className="field">
              <label>Timeframe</label>
              <select value={form.timeframe} onChange={(e) => update('timeframe', e.target.value)}>
                {TIMEFRAMES.map((tf) => (
                  <option key={tf} value={tf}>{tf}</option>
                ))}
              </select>
            </div>
            <div className="field">
              <label>Velas</label>
              <input type="number" value={form.bars} onChange={(e) => update('bars', e.target.value)} min="200" />
            </div>
            <div className="field">
              <label>Riesgo %</label>
              <input type="number" step="0.1" value={form.risk_pct} onChange={(e) => update('risk_pct', e.target.value)} />
            </div>
            <div className="field">
              <label>Spread (pts)</label>
              <input
                type="number"
                placeholder="auto"
                value={form.spread_points}
                onChange={(e) => update('spread_points', e.target.value)}
              />
            </div>
            <div className="field">
              <label>Comisión</label>
              <input
                type="number"
                step="0.5"
                value={form.commission_per_lot}
                onChange={(e) => update('commission_per_lot', e.target.value)}
              />
            </div>
            <div className="field">
              <label>EMA rápida</label>
              <input type="number" value={form.ema_fast} onChange={(e) => update('ema_fast', e.target.value)} />
            </div>
            <div className="field">
              <label>EMA lenta</label>
              <input type="number" value={form.ema_slow} onChange={(e) => update('ema_slow', e.target.value)} />
            </div>
            <div className="field">
              <label>RSI long máx.</label>
              <input type="number" value={form.rsi_long_max} onChange={(e) => update('rsi_long_max', e.target.value)} />
            </div>
            <div className="field">
              <label>RSI short mín.</label>
              <input type="number" value={form.rsi_short_min} onChange={(e) => update('rsi_short_min', e.target.value)} />
            </div>
            <div className="field">
              <label>SL (x ATR)</label>
              <input type="number" step="0.1" value={form.sl_atr} onChange={(e) => update('sl_atr', e.target.value)} />
            </div>
            <div className="field">
              <label>TP (x ATR)</label>
              <input type="number" step="0.1" value={form.tp_atr} onChange={(e) => update('tp_atr', e.target.value)} />
            </div>
            <div className="field">
              <label>Enfriamiento</label>
              <input type="number" value={form.cooldown_bars} onChange={(e) => update('cooldown_bars', e.target.value)} />
            </div>
          </div>

          <div className="row between" style={{ marginTop: 16 }}>
            <div className="card-hint">
              {result?.params ? `${result.params.symbol || 'BTC'} · ${result.params.bars} velas · spread ${num(result.params.spread_points, 0)} pts` : 'Sin ejecutar'}
            </div>
            <button className="btn primary" onClick={execute} disabled={running}>
              {running ? <span className="spinner" /> : null}
              {running ? 'Corriendo…' : 'Ejecutar backtest'}
            </button>
          </div>
        </div>

        <div className="card">
          <div className="card-head">
            <div className="card-title">Historial</div>
            <div className="card-hint">{history.length} corridas</div>
          </div>
          <div className="table-wrap" style={{ maxHeight: 380 }}>
            <table>
              <thead>
                <tr>
                  <th>Fecha</th>
                  <th>TF</th>
                  <th>Trades</th>
                  <th>P&amp;L</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {history.length ? (
                  history.map((run) => (
                    <tr key={run.id}>
                      <td className="muted">{dateTime(run.created_at)}</td>
                      <td>{run.params?.timeframe || '—'}</td>
                      <td className="num">{run.metrics?.trades ?? '—'}</td>
                      <td className={`num ${(run.metrics?.net_pnl ?? 0) >= 0 ? 'pos' : 'neg'}`}>
                        {signedUsd(run.metrics?.net_pnl ?? 0)}
                      </td>
                      <td>
                        <button className="btn sm ghost" onClick={() => loadRun(run.id)}>Ver</button>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={5} className="empty">Sin corridas todavía.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {result ? (
        <>
          <MetricGrid metrics={metrics} />

          <div className="grid two">
            <div className="card">
              <div className="card-head">
                <div className="card-title">Curva de equity</div>
                <div className="card-hint">
                  {result.params?.source === 'sim' ? 'datos simulados' : 'datos MT5'} · {dateTime(result.params?.from || result.equity_curve?.[0]?.time)}
                </div>
              </div>
              <EquityChart data={result.equity_curve || metrics?.equity_curve || []} height={260} />
            </div>

            <div className="card">
              <div className="card-head">
                <div className="card-title">Resumen</div>
                <div className="card-hint">run {result.run_id}</div>
              </div>
              <div className="kv"><span>Operaciones</span><span>{metrics?.trades}</span></div>
              <div className="kv"><span>Ganadoras / perdedoras</span><span>{metrics?.wins} / {metrics?.losses}</span></div>
              <div className="kv"><span>Mejor trade</span><span className="pos">{signedUsd(metrics?.best_trade)}</span></div>
              <div className="kv"><span>Peor trade</span><span className="neg">{signedUsd(metrics?.worst_trade)}</span></div>
              <div className="kv"><span>Racha ganadora</span><span>{metrics?.max_win_streak}</span></div>
              <div className="kv"><span>Racha perdedora</span><span>{metrics?.max_loss_streak}</span></div>
              <div className="kv"><span>Drawdown máximo</span><span>{signedUsd(-(metrics?.max_drawdown ?? 0))}</span></div>
              <div className="kv"><span>Equity final</span><span>{signedUsd(metrics?.final_equity)}</span></div>
            </div>
          </div>

          <div className="card">
            <div className="card-head">
              <div className="card-title">Operaciones del backtest</div>
              <div className="card-hint">últimas {Math.min(result.trades?.length || 0, 300)}</div>
            </div>
            <TradesTable trades={result.trades || []} />
          </div>
        </>
      ) : null}
    </div>
  )
}
