import {
  Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { money, timeShort } from '../lib/format.js'

function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div
      style={{
        background: '#0b1119',
        border: '1px solid #24313f',
        borderRadius: 10,
        padding: '8px 12px',
        fontSize: 12,
        boxShadow: '0 12px 30px rgba(0,0,0,.45)',
      }}
    >
      <div style={{ color: '#8494a9', marginBottom: 4 }}>{timeShort(label)}</div>
      <div style={{ fontWeight: 700 }}>${money(payload[0].value, 2)}</div>
    </div>
  )
}

export default function EquityChart({ data = [], height = 240, color = '#16c784' }) {
  const points = (data || []).map((point, index) => ({
    ...point,
    equity: Number(point.equity ?? point.value ?? 0),
    label: point.time ?? index,
  }))

  if (points.length < 2) {
    return <div className="empty">Todavía no hay operaciones cerradas para dibujar la curva.</div>
  }

  const gradientId = `eq-${color.replace('#', '')}`

  return (
    <div className="chart-box" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={points} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.35} />
              <stop offset="100%" stopColor={color} stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="#1a2431" strokeDasharray="3 6" vertical={false} />
          <XAxis
            dataKey="label"
            tickFormatter={(value) => timeShort(value)}
            tick={{ fill: '#5d6b7e', fontSize: 10.5 }}
            axisLine={false}
            tickLine={false}
            minTickGap={40}
          />
          <YAxis
            domain={['auto', 'auto']}
            tick={{ fill: '#5d6b7e', fontSize: 10.5 }}
            axisLine={false}
            tickLine={false}
            width={58}
            tickFormatter={(value) => money(value, 0)}
          />
          <Tooltip content={<ChartTooltip />} />
          <Area
            type="monotone"
            dataKey="equity"
            stroke={color}
            strokeWidth={2}
            fill={`url(#${gradientId})`}
            isAnimationActive={false}
            dot={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
