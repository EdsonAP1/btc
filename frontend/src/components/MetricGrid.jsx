import { num, pct, signedUsd, tone, usd } from '../lib/format.js'

const ITEMS = [
  { key: 'net_pnl', label: 'P&L neto', format: (v) => signedUsd(v), tone: true },
  { key: 'return_pct', label: 'Retorno', format: (v) => `${num(v, 2)}%`, tone: true },
  { key: 'winrate', label: 'Winrate', format: (v) => pct(v, 1) },
  { key: 'trades', label: 'Operaciones', format: (v) => num(v, 0) },
  { key: 'profit_factor', label: 'Profit factor', format: (v) => num(v, 2), tone: false },
  { key: 'expectancy', label: 'Expectancy', format: (v) => signedUsd(v), tone: true },
  { key: 'avg_r', label: 'R promedio', format: (v) => `${num(v, 2)}R`, tone: true },
  { key: 'max_drawdown_pct', label: 'Máx. drawdown', format: (v) => `${num(v, 2)}%`, tone: false },
  { key: 'sharpe', label: 'Sharpe', format: (v) => num(v, 2), tone: true },
  { key: 'final_equity', label: 'Equity final', format: (v) => usd(v) },
]

export default function MetricGrid({ metrics }) {
  if (!metrics) return null
  return (
    <div className="grid stats">
      {ITEMS.map((item) => {
        const value = metrics[item.key]
        return (
          <div className="card stat" key={item.key}>
            <div className="stat-label">{item.label}</div>
            <div className={`stat-value num ${item.tone ? tone(value) : ''}`} style={{ fontSize: 21 }}>
              {value === undefined || value === null ? '—' : item.format(value)}
            </div>
          </div>
        )
      })}
    </div>
  )
}
