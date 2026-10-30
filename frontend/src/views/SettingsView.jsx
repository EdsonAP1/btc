import { useEffect, useState } from 'react'
import { getConfig, getSymbol, mlStatus, patchConfig, rescanSymbol, trainMl } from '../api.js'
import { num } from '../lib/format.js'

const TIMEFRAMES = ['M1', 'M5', 'M15', 'M30', 'H1', 'H4', 'D1']

export default function SettingsView({ onSaved }) {
  const [config, setConfig] = useState(null)
  const [symbol, setSymbol] = useState(null)
  const [ml, setMl] = useState(null)
  const [saving, setSaving] = useState(false)
  const [notice, setNotice] = useState(null)
  const [error, setError] = useState(null)
  const [training, setTraining] = useState(false)

  const load = async () => {
    try {
      const [cfg, sym, mlInfo] = await Promise.all([getConfig(), getSymbol(), mlStatus()])
      setConfig(cfg)
      setSymbol(sym)
      setMl(mlInfo)
      setError(null)
    } catch (err) {
      setError(err.message)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const setField = (section, key, value) => {
    setConfig((prev) => {
      if (!prev) return prev
      if (!section) return { ...prev, [key]: value }
      return { ...prev, [section]: { ...prev[section], [key]: value } }
    })
  }

  const toNumber = (value) => (value === '' || value === null ? null : Number(value))

  const setMgmt = (group, key, value) =>
    setConfig((prev) => ({
      ...prev,
      management: {
        ...prev.management,
        [group]: { ...(prev.management?.[group] || {}), [key]: value },
      },
    }))

  const setPartialStep = (key, value) =>
    setConfig((prev) => {
      const steps = prev.management?.partials?.steps || []
      const first = steps[0] || { at_r: 1, pct: 50 }
      return {
        ...prev,
        management: {
          ...prev.management,
          partials: { ...prev.management.partials, steps: [{ ...first, [key]: value }] },
        },
      }
    })

  const save = async () => {
    setSaving(true)
    setError(null)
    setNotice(null)
    try {
      const res = await patchConfig(config)
      setConfig(res.config)
      setNotice(res.note || 'Configuración guardada.')
      onSaved?.(res.config)
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  const rescan = async () => {
    try {
      const data = await rescanSymbol()
      setSymbol(data)
      setNotice(data.connected ? `Símbolo detectado: ${data.name}` : 'MT5 no conectado.')
    } catch (err) {
      setError(err.message)
    }
  }

  const train = async () => {
    setTraining(true)
    setError(null)
    try {
      const res = await trainMl({ timeframe: config?.timeframe, bars: 8000 })
      setMl({ trained: true, metrics: res.metrics })
      setNotice(`Modelo entrenado · accuracy walk-forward ${num(res.metrics.walk_forward_accuracy * 100, 1)}%`)
    } catch (err) {
      setError(err.message)
    } finally {
      setTraining(false)
    }
  }

  if (!config) {
    return <div className="banner info">{error || 'Cargando configuración…'}</div>
  }

  const info = symbol?.info || {}

  return (
    <div className="stack">
      {error ? <div className="banner">{error}</div> : null}
      {notice ? <div className="banner info">{notice}</div> : null}

      <div className="grid two">
        <div className="card">
          <div className="card-head">
            <div className="card-title">Símbolo y conexión</div>
            <button className="btn sm" onClick={rescan}>Reescanear MT5</button>
          </div>

          <div className="kv"><span>Símbolo en uso</span><span className="num">{symbol?.name || '—'}</span></div>
          <div className="kv"><span>Detección</span><span>{symbol?.auto_detected ? 'automática' : 'manual'}</span></div>
          <div className="kv"><span>Dígitos / punto</span><span className="num">{info.digits ?? '—'} / {info.point ?? '—'}</span></div>
          <div className="kv"><span>Spread actual</span><span className="num">{info.spread ?? '—'} pts</span></div>
          <div className="kv"><span>Lote mínimo</span><span className="num">{info.volume_min ?? '—'}</span></div>
          <div className="kv"><span>Contrato</span><span className="num">{info.contract_size ?? '—'}</span></div>

          {symbol?.candidates?.length ? (
            <div className="card-hint" style={{ marginTop: 10 }}>
              Candidatos: {symbol.candidates.map((c) => `${c.name} (${c.score})`).join(' · ')}
            </div>
          ) : null}

          <div className="form-grid" style={{ marginTop: 14 }}>
            <div className="field">
              <label>Detección</label>
              <select value={config.symbol.mode} onChange={(e) => setField('symbol', 'mode', e.target.value)}>
                <option value="auto">Automática</option>
                <option value="manual">Manual</option>
              </select>
            </div>
            <div className="field">
              <label>Nombre manual</label>
              <input
                placeholder="BTCUSD"
                value={config.symbol.name || ''}
                onChange={(e) => setField('symbol', 'name', e.target.value || null)}
                disabled={config.symbol.mode !== 'manual'}
              />
            </div>
            <div className="field">
              <label>Modo del bot</label>
              <select value={config.mode} onChange={(e) => setField(null, 'mode', e.target.value)}>
                <option value="live">Cuenta MT5 (demo/real)</option>
                <option value="paper">Paper (simulado)</option>
                <option value="sim">Simulado (sin MT5)</option>
              </select>
            </div>
            <div className="field">
              <label>Timeframe</label>
              <select value={config.timeframe} onChange={(e) => setField(null, 'timeframe', e.target.value)}>
                {TIMEFRAMES.map((tf) => (
                  <option key={tf} value={tf}>{tf}</option>
                ))}
              </select>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card-head">
            <div className="card-title">Estrategia</div>
            <div className="card-hint">{config.strategy.name}</div>
          </div>
          <div className="form-grid">
            <div className="field" style={{ gridColumn: '1 / -1' }}>
              <label>Estrategia activa</label>
              <select value={config.strategy.name} onChange={(e) => setField('strategy', 'name', e.target.value)}>
                <option value="ema_rsi_atr">EMA + RSI + ATR (tendencia)</option>
                <option value="donchian">Donchian (ruptura de canal)</option>
                <option value="mean_reversion">Reversión a la media (Bollinger)</option>
              </select>
            </div>

            {config.strategy.name === 'ema_rsi_atr' ? (
              <>
                <div className="field">
                  <label>EMA rápida</label>
                  <input type="number" value={config.strategy.ema_fast} onChange={(e) => setField('strategy', 'ema_fast', Number(e.target.value))} />
                </div>
                <div className="field">
                  <label>EMA lenta</label>
                  <input type="number" value={config.strategy.ema_slow} onChange={(e) => setField('strategy', 'ema_slow', Number(e.target.value))} />
                </div>
                <div className="field">
                  <label>RSI máx. long</label>
                  <input type="number" value={config.strategy.rsi_long_max} onChange={(e) => setField('strategy', 'rsi_long_max', Number(e.target.value))} />
                </div>
                <div className="field">
                  <label>RSI mín. short</label>
                  <input type="number" value={config.strategy.rsi_short_min} onChange={(e) => setField('strategy', 'rsi_short_min', Number(e.target.value))} />
                </div>
              </>
            ) : null}

            {config.strategy.name === 'donchian' ? (
              <>
                <div className="field">
                  <label>Canal (velas)</label>
                  <input type="number" value={config.strategy.donchian_period} onChange={(e) => setField('strategy', 'donchian_period', Number(e.target.value))} />
                </div>
                <div className="field">
                  <label>EMA tendencia (0=off)</label>
                  <input type="number" value={config.strategy.trend_ema ?? 0} onChange={(e) => setField('strategy', 'trend_ema', Number(e.target.value))} />
                </div>
              </>
            ) : null}

            {config.strategy.name === 'mean_reversion' ? (
              <>
                <div className="field">
                  <label>Bollinger (velas)</label>
                  <input type="number" value={config.strategy.bb_period} onChange={(e) => setField('strategy', 'bb_period', Number(e.target.value))} />
                </div>
                <div className="field">
                  <label>Desvíos (std)</label>
                  <input type="number" step="0.1" value={config.strategy.bb_std} onChange={(e) => setField('strategy', 'bb_std', Number(e.target.value))} />
                </div>
                <div className="field">
                  <label>RSI compra ≤</label>
                  <input type="number" value={config.strategy.mr_rsi_low} onChange={(e) => setField('strategy', 'mr_rsi_low', Number(e.target.value))} />
                </div>
                <div className="field">
                  <label>RSI venta ≥</label>
                  <input type="number" value={config.strategy.mr_rsi_high} onChange={(e) => setField('strategy', 'mr_rsi_high', Number(e.target.value))} />
                </div>
              </>
            ) : null}

            <div className="field">
              <label>RSI período</label>
              <input type="number" value={config.strategy.rsi_period} onChange={(e) => setField('strategy', 'rsi_period', Number(e.target.value))} />
            </div>
            <div className="field">
              <label>ATR período</label>
              <input type="number" value={config.strategy.atr_period} onChange={(e) => setField('strategy', 'atr_period', Number(e.target.value))} />
            </div>
            <div className="field">
              <label>SL (x ATR)</label>
              <input type="number" step="0.1" value={config.strategy.sl_atr} onChange={(e) => setField('strategy', 'sl_atr', Number(e.target.value))} />
            </div>
            <div className="field">
              <label>TP (x ATR)</label>
              <input type="number" step="0.1" value={config.strategy.tp_atr} onChange={(e) => setField('strategy', 'tp_atr', Number(e.target.value))} />
            </div>
            <div className="field">
              <label>Enfriamiento</label>
              <input type="number" value={config.strategy.cooldown_bars} onChange={(e) => setField('strategy', 'cooldown_bars', Number(e.target.value))} />
            </div>
            <div className="field">
              <label>Filtro ML</label>
              <select value={config.strategy.use_ml ? 'si' : 'no'} onChange={(e) => setField('strategy', 'use_ml', e.target.value === 'si')}>
                <option value="no">Desactivado</option>
                <option value="si">Activado</option>
              </select>
            </div>
            <div className="field">
              <label>Umbral ML</label>
              <input type="number" step="0.01" value={config.strategy.ml_threshold} onChange={(e) => setField('strategy', 'ml_threshold', Number(e.target.value))} />
            </div>
          </div>
        </div>
      </div>

      <div className="grid two">
        <div className="card">
          <div className="card-head">
            <div className="card-title">Riesgo</div>
            <div className="card-hint">límites duros del bot</div>
          </div>
          <div className="form-grid">
            <div className="field">
              <label>Riesgo/trade %</label>
              <input type="number" step="0.1" value={config.risk.risk_pct} onChange={(e) => setField('risk', 'risk_pct', Number(e.target.value))} />
            </div>
            <div className="field">
              <label>Máx. posiciones</label>
              <input type="number" value={config.risk.max_positions} onChange={(e) => setField('risk', 'max_positions', Number(e.target.value))} />
            </div>
            <div className="field">
              <label>Pérdida diaria %</label>
              <input type="number" step="0.1" value={config.risk.max_daily_loss_pct} onChange={(e) => setField('risk', 'max_daily_loss_pct', Number(e.target.value))} />
            </div>
            <div className="field">
              <label>Spread máx.</label>
              <input
                type="number"
                placeholder="auto"
                value={config.risk.max_spread_points ?? ''}
                onChange={(e) => setField('risk', 'max_spread_points', toNumber(e.target.value))}
              />
            </div>
            <div className="field">
              <label>Lote mínimo</label>
              <input type="number" step="0.01" value={config.risk.lot_min} onChange={(e) => setField('risk', 'lot_min', Number(e.target.value))} />
            </div>
            <div className="field">
              <label>Lote máximo</label>
              <input type="number" step="0.01" value={config.risk.lot_max} onChange={(e) => setField('risk', 'lot_max', Number(e.target.value))} />
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card-head">
            <div className="card-title">Modelo ML</div>
            <button className="btn sm" onClick={train} disabled={training}>
              {training ? 'Entrenando…' : 'Entrenar'}
            </button>
          </div>
          {ml?.trained ? (
            <>
              <div className="kv"><span>Accuracy walk-forward</span><span>{num((ml.metrics?.walk_forward_accuracy ?? 0) * 100, 1)}%</span></div>
              <div className="kv"><span>Base rate</span><span>{num((ml.metrics?.base_rate ?? 0) * 100, 1)}%</span></div>
              <div className="kv"><span>Muestras</span><span>{ml.metrics?.samples ?? ml.samples ?? '—'}</span></div>
              <div className="kv"><span>Entrenado</span><span>{ml.trained_at ? String(ml.trained_at).slice(0, 16).replace('T', ' ') : '—'}</span></div>
            </>
          ) : (
            <div className="empty">Sin modelo entrenado. Entrená con datos históricos de MT5 para activar el filtro.</div>
          )}
          <div className="card-hint" style={{ marginTop: 10 }}>
            El filtro ML solo se aplica si “Filtro ML” está activado en la estrategia.
          </div>
        </div>
      </div>

      <div className="grid two">
        <div className="card">
          <div className="card-head">
            <div className="card-title">Gestión de salida</div>
            <div className="card-hint">break-even, trailing y parciales</div>
          </div>
          <div className="form-grid">
            <div className="field">
              <label>Break-even</label>
              <select value={config.management.break_even.enabled ? 'si' : 'no'} onChange={(e) => setMgmt('break_even', 'enabled', e.target.value === 'si')}>
                <option value="si">Activado</option>
                <option value="no">Desactivado</option>
              </select>
            </div>
            <div className="field">
              <label>BE desde (ATR)</label>
              <input type="number" step="0.1" value={config.management.break_even.trigger_atr} onChange={(e) => setMgmt('break_even', 'trigger_atr', Number(e.target.value))} />
            </div>
            <div className="field">
              <label>BE offset (ATR)</label>
              <input type="number" step="0.05" value={config.management.break_even.offset_atr} onChange={(e) => setMgmt('break_even', 'offset_atr', Number(e.target.value))} />
            </div>
            <div className="field">
              <label>Trailing</label>
              <select value={config.management.trailing.enabled ? 'si' : 'no'} onChange={(e) => setMgmt('trailing', 'enabled', e.target.value === 'si')}>
                <option value="si">Activado</option>
                <option value="no">Desactivado</option>
              </select>
            </div>
            <div className="field">
              <label>Trailing desde (ATR)</label>
              <input type="number" step="0.1" value={config.management.trailing.start_atr} onChange={(e) => setMgmt('trailing', 'start_atr', Number(e.target.value))} />
            </div>
            <div className="field">
              <label>Trailing dist. (ATR)</label>
              <input type="number" step="0.1" value={config.management.trailing.distance_atr} onChange={(e) => setMgmt('trailing', 'distance_atr', Number(e.target.value))} />
            </div>
            <div className="field">
              <label>Parciales</label>
              <select value={config.management.partials.enabled ? 'si' : 'no'} onChange={(e) => setMgmt('partials', 'enabled', e.target.value === 'si')}>
                <option value="si">Activado</option>
                <option value="no">Desactivado</option>
              </select>
            </div>
            <div className="field">
              <label>Parcial a (R)</label>
              <input type="number" step="0.1" value={config.management.partials.steps?.[0]?.at_r ?? 1} onChange={(e) => setPartialStep('at_r', Number(e.target.value))} />
            </div>
            <div className="field">
              <label>Parcial %</label>
              <input type="number" step="5" value={config.management.partials.steps?.[0]?.pct ?? 50} onChange={(e) => setPartialStep('pct', Number(e.target.value))} />
            </div>
          </div>
          <div className="card-hint" style={{ marginTop: 10 }}>
            Con SL de 2 ATR, 1R = 2 ATR. Cerrar 50% a 1R baja el riesgo a la mitad.
          </div>
        </div>

        <div className="card">
          <div className="card-head">
            <div className="card-title">Límites de cuenta</div>
            <div className="card-hint">frenan el bot automáticamente</div>
          </div>
          <div className="form-grid">
            <div className="field">
              <label>Trades por día</label>
              <input type="number" value={config.risk.max_trades_per_day ?? 0} onChange={(e) => setField('risk', 'max_trades_per_day', Number(e.target.value))} />
            </div>
            <div className="field">
              <label>Drawdown máx. %</label>
              <input type="number" step="0.5" value={config.risk.max_drawdown_pct ?? 0} onChange={(e) => setField('risk', 'max_drawdown_pct', Number(e.target.value))} />
            </div>
            <div className="field">
              <label>Al alcanzar DD</label>
              <select value={config.risk.halt_on_drawdown ? 'si' : 'no'} onChange={(e) => setField('risk', 'halt_on_drawdown', e.target.value === 'si')}>
                <option value="si">Detener el bot</option>
                <option value="no">Solo bloquear entradas</option>
              </select>
            </div>
            <div className="field">
              <label>Margen libre mín. %</label>
              <input type="number" step="5" value={config.risk.min_free_margin_pct ?? 0} onChange={(e) => setField('risk', 'min_free_margin_pct', Number(e.target.value))} />
            </div>
          </div>
          <div className="card-hint" style={{ marginTop: 10 }}>
            El drawdown se mide desde el pico de equity guardado (sobrevive reinicios).
          </div>
        </div>
      </div>

      <div className="row between">
        <div className="card-hint">Los cambios de símbolo o timeframe requieren reiniciar el bot.</div>
        <button className="btn primary" onClick={save} disabled={saving}>
          {saving ? 'Guardando…' : 'Guardar configuración'}
        </button>
      </div>
    </div>
  )
}
