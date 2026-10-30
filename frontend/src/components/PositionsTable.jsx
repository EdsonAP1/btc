import { money, num, signedUsd, tone } from '../lib/format.js'

export default function PositionsTable({ positions = [] }) {
  if (!positions.length) {
    return <div className="empty">Sin posiciones abiertas. El bot está esperando señal.</div>
  }

  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Ticket</th>
            <th>Lado</th>
            <th>Vol.</th>
            <th>Entrada</th>
            <th>Actual</th>
            <th>SL</th>
            <th>TP</th>
            <th>P&amp;L</th>
          </tr>
        </thead>
        <tbody>
          {positions.map((position) => {
            const pnl = Number(position.profit || 0)
            return (
              <tr key={position.ticket}>
                <td className="muted num">#{position.ticket}</td>
                <td>
                  <span className={`tag ${position.side}`}>{position.side === 'buy' ? 'COMPRA' : 'VENTA'}</span>
                </td>
                <td className="num">{num(position.volume, 2)}</td>
                <td className="num">{money(position.open_price, 2)}</td>
                <td className="num">{money(position.current_price, 2)}</td>
                <td className="num muted">{position.sl ? money(position.sl, 2) : '—'}</td>
                <td className="num muted">{position.tp ? money(position.tp, 2) : '—'}</td>
                <td className={`num ${tone(pnl)}`}>{signedUsd(pnl)}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
