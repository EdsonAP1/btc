export default function StatCard({ label, value, sub, tone = '', accent = false }) {
  return (
    <div className={`card stat${accent ? ' accent' : ''}`}>
      <div className="stat-label">{label}</div>
      <div className={`stat-value num ${tone}`}>{value}</div>
      {sub ? <div className="stat-foot">{sub}</div> : null}
    </div>
  )
}
