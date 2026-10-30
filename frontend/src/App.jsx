import { useEffect, useMemo, useState } from 'react'
import { panic, startBot, stopBot } from './api.js'
import { useLive } from './hooks/useLive.js'
import { money, price, signedUsd, tone } from './lib/format.js'
import Dashboard from './views/Dashboard.jsx'
import TradesView from './views/TradesView.jsx'
import BacktestView from './views/BacktestView.jsx'
import SettingsView from './views/SettingsView.jsx'

const TABS = [
  { key: 'dashboard', label: 'Panel', icon: '◉', title: 'Panel de control', sub: 'Estado en vivo del bot y del mercado' },
  { key: 'trades', label: 'Operaciones', icon: '≣', title: 'Operaciones', sub: 'Historial, métricas y rendimiento por hora' },
  { key: 'backtest', label: 'Backtest', icon: '⌁', title: 'Backtesting', sub: 'Probá la estrategia con datos históricos' },
  { key: 'settings', label: 'Ajustes', icon: '⚙', title: 'Configuración', sub: 'Símbolo, estrategia, riesgo y modelo ML' },
]

const MODES = [
  { value: 'live', label: 'Cuenta MT5' },
  { value: 'paper', label: 'Paper' },
  { value: 'sim', label: 'Simulado' },
]

export default function App() {
  const [tab, setTab] = useState(() => {
    const fromHash = window.location.hash.replace('#', '')
    return TABS.some((item) => item.key === fromHash) ? fromHash : 'dashboard'
  })
  const [mode, setMode] = useState('live')
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState(null)
  const { status, connected, error } = useLive()

  useEffect(() => {
    const onHashChange = () => {
      const fromHash = window.location.hash.replace('#', '')
      if (TABS.some((item) => item.key === fromHash)) setTab(fromHash)
    }
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  const changeTab = (key) => {
    setTab(key)
    window.location.hash = key
  }

  const bot = status?.bot || {}
  const market = status?.market || {}
  const account = status?.account || {}
  const running = bot.state === 'running' || bot.state === 'starting'
  const mt5 = status?.mt5 || {}

  const activeTab = useMemo(() => TABS.find((item) => item.key === tab) || TABS[0], [tab])

  const runAction = async (fn, successMessage) => {
    setBusy(true)
    setActionError(null)
    try {
      await fn()
    } catch (err) {
      setActionError(err.message || successMessage || 'La acción falló')
    } finally {
      setBusy(false)
    }
  }

  const handleStart = () =>
    runAction(async () => {
      const isReal = status?.account?.type === 'real'
      if (mode === 'live' && isReal) {
        const ok = window.confirm(
          'La cuenta conectada en MT5 es REAL.\n\nEl bot va a enviar órdenes con dinero real.\n¿Querés continuar?',
        )
        if (!ok) return
        await startBot(mode, true)
        return
      }
      await startBot(mode)
    })

  const handleStop = () =>
    runAction(async () => {
      await stopBot(false)
    })

  const handlePanic = () =>
    runAction(async () => {
      await panic()
    })

  const dailyPnl = Number(status?.today?.pnl || 0)

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-logo">₿</div>
          <div>
            <div className="brand-title">BTC Bot</div>
            <div className="brand-sub">MT5 · {status?.symbol?.name || 'BTC'}</div>
          </div>
        </div>

        <nav className="nav">
          {TABS.map((item) => (
            <button
              key={item.key}
              className={`nav-item ${tab === item.key ? 'active' : ''}`}
              onClick={() => changeTab(item.key)}
            >
              <span className="nav-icon">{item.icon}</span>
              {item.label}
            </button>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className={`pill ${mt5.connected ? 'ok' : 'bad'}`} style={{ marginBottom: 8 }}>
            <span className="dot" />
            {mt5.connected ? 'MT5 conectado' : 'MT5 offline'}
          </div>
          <div className={`pill ${running ? 'ok live' : ''}`}>
            <span className="dot" />
            {running ? 'Bot operando' : 'Bot detenido'}
          </div>
          <div style={{ marginTop: 10 }}>
            {account.login ? `Cuenta ${account.login}` : 'Cuenta paper'}
            {account.type ? ` · ${account.type.toUpperCase()}` : ''}
          </div>
          <div>{account.server || '—'}</div>
        </div>
      </aside>

      <main className="main">
        <div className="main-inner">
          <header className="topbar">
            <div>
              <div className="page-title">{activeTab.title}</div>
              <div className="page-sub">{activeTab.sub}</div>
            </div>

            <div className="topbar-actions">
              <div className="price-block">
                <span className="price num">{price(market.bid, 2)}</span>
                <span className="price-symbol">USD</span>
                <span className={`num ${tone(dailyPnl)}`} style={{ fontSize: 13 }}>
                  {signedUsd(dailyPnl)}
                </span>
              </div>

              {account.type ? (
                <span className={`pill ${account.type === 'real' ? 'bad' : account.type === 'demo' ? 'ok' : ''}`}>
                  <span className="dot" />
                  {account.type === 'real' ? 'REAL' : account.type === 'demo' ? 'DEMO' : account.type.toUpperCase()}
                </span>
              ) : null}

              {running ? (
                <span className={`pill ${bot.mode === 'live' ? 'warn' : 'ok live'}`}>
                  <span className="dot" />
                  {(bot.mode || mode).toUpperCase()}
                </span>
              ) : null}

              {running ? (
                <>
                  <button className="btn" onClick={handleStop} disabled={busy}>Detener</button>
                  <button className="btn danger" onClick={handlePanic} disabled={busy}>Cerrar todo</button>
                </>
              ) : (
                <>
                  <select
                    className="btn"
                    style={{ paddingRight: 8 }}
                    value={mode}
                    onChange={(e) => setMode(e.target.value)}
                  >
                    {MODES.map((item) => (
                      <option key={item.value} value={item.value}>{item.label}</option>
                    ))}
                  </select>
                  <button className="btn primary" onClick={handleStart} disabled={busy}>
                    {busy ? 'Iniciando…' : 'Iniciar bot'}
                  </button>
                </>
              )}
            </div>
          </header>

          {actionError ? <div className="banner" style={{ marginBottom: 14 }}>{actionError}</div> : null}
          {error && !status ? <div className="banner" style={{ marginBottom: 14 }}>Backend no responde: {error}</div> : null}
          {bot.error ? <div className="banner" style={{ marginBottom: 14 }}>{bot.error}</div> : null}
          {connected === false && status ? (
            <div className="banner info" style={{ marginBottom: 14 }}>
              WebSocket desconectado; el panel se actualiza por polling cada 5 s.
            </div>
          ) : null}

          {tab === 'dashboard' ? <Dashboard status={status} /> : null}
          {tab === 'trades' ? <TradesView /> : null}
          {tab === 'backtest' ? <BacktestView /> : null}
          {tab === 'settings' ? <SettingsView onSaved={() => {}} /> : null}

          <footer className="card-hint" style={{ marginTop: 22, textAlign: 'center' }}>
            Equity ${money(account.equity ?? 0, 2)} · balance ${money(account.balance ?? 0, 2)} ·{' '}
            {status?.symbol?.name || 'BTC'} {bot.timeframe || 'M5'} · modo {bot.mode || 'detenido'}
          </footer>
        </div>
      </main>
    </div>
  )
}
