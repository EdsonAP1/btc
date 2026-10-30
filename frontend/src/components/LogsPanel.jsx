import { timeShort } from '../lib/format.js'

export default function LogsPanel({ logs = [] }) {
  if (!logs.length) {
    return <div className="empty">Sin actividad registrada.</div>
  }
  return (
    <div className="logs">
      {logs
        .slice()
        .reverse()
        .map((entry, index) => (
          <div className="log-row" key={`${entry.time}-${index}`}>
            <span className="log-time">{timeShort(entry.time)}</span>
            <span className={`log-level ${entry.level}`}>{entry.level}</span>
            <span className="log-msg">{entry.message}</span>
          </div>
        ))}
    </div>
  )
}
