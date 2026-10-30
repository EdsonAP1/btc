import { dateTime, money, num, signedUsd, tone } from '../lib/format.js'

export default function TradesTable({ trades = [], empty = 'Todavía no hay operaciones.', limit }) {
  const rows = limit ? trades.slice(0, limit) : trades

  if (!rows.length) {
    return <div className="empty">{empty}</div>
  }

  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Hora</th>
            <th>Lado</th>
            <th>Vol.</th>
            <th>Entrada</th>
            <th>Salida</th>
            <th>P&amp;L</th>
            <th>R</th>
            <th>Estado</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((trade) => {
            const isOpen = trade.status === 'open'
            const pnl = Number(trade.pnl || 0)
            return (
              <tr key={trade.id ?? `${trade.ticket}-${trade.open_time}`}>
                <td className="muted">{dateTime(trade.close_time || trade.open_time)}</td>
                <td>
                  <span className={`tag ${trade.side}`}>{trade.side === 'buy' ? 'COMPRA' : 'VENTA'}</span>
                </td>
                <td className="num">{num(trade.volume, 2)}</td>
                <td className="num">{money(trade.open_price, 2)}</td>
                <td className="num">{isOpen ? '—' : money(trade.close_price, 2)}</td>
                <td className={`num ${isOpen ? 'muted' : tone(pnl)}`}>{isOpen ? '—' : signedUsd(pnl)}</td>
                <td className={`num ${tone(trade.r_multiple)}`}>
                  {trade.r_multiple === null || trade.r_multiple === undefined ? '—' : `${num(trade.r_multiple, 2)}R`}
                </td>
                <td>
                  <span className={`tag ${isOpen ? 'open' : 'closed'}`}>{isOpen ? 'ABIERTA' : 'CERRADA'}</span>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
