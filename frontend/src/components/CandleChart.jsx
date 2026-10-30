import { useEffect, useRef, useState } from 'react'
import { money } from '../lib/format.js'

const UP = '#16c784'
const DOWN = '#ea3943'

export default function CandleChart({ candles = [], height = 260 }) {
  const wrapRef = useRef(null)
  const [width, setWidth] = useState(720)

  useEffect(() => {
    const el = wrapRef.current
    if (!el) return
    const observer = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect?.width
      if (w) setWidth(w)
    })
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  if (!candles.length) {
    return <div className="empty">Sin velas todavía…</div>
  }

  const padL = 10
  const padR = 74
  const padT = 12
  const padB = 24
  const innerW = Math.max(20, width - padL - padR)
  const innerH = height - padT - padB

  const highs = candles.map((c) => c.high)
  const lows = candles.map((c) => c.low)
  let max = Math.max(...highs)
  let min = Math.min(...lows)
  const margin = (max - min) * 0.08 || 1
  max += margin
  min -= margin

  const y = (value) => padT + ((max - value) / (max - min)) * innerH
  const step = innerW / candles.length
  const bodyW = Math.max(1.4, step * 0.62)
  const x = (index) => padL + index * step + step / 2

  const gridCount = 5
  const gridLines = Array.from({ length: gridCount }, (_, i) => {
    const value = min + ((max - min) * i) / (gridCount - 1)
    return { value, y: y(value) }
  })

  const last = candles[candles.length - 1]
  const lastY = y(last.close)
  const labelEvery = Math.max(1, Math.floor(candles.length / 6))

  return (
    <div ref={wrapRef} style={{ width: '100%' }}>
      <svg width={width} height={height} role="img" aria-label="Gráfico de velas BTC">
        <defs>
          <linearGradient id="candleFade" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#f7931a" stopOpacity="0.12" />
            <stop offset="100%" stopColor="#f7931a" stopOpacity="0" />
          </linearGradient>
        </defs>

        {gridLines.map((line, index) => (
          <g key={index}>
            <line x1={padL} x2={padL + innerW} y1={line.y} y2={line.y} stroke="#1a2431" strokeWidth="1" />
            <text x={padL + innerW + 8} y={line.y + 4} fill="#6b7a8d" fontSize="10.5" fontFamily="monospace">
              {money(line.value, 1)}
            </text>
          </g>
        ))}

        {candles.map((candle, index) => {
          const up = candle.close >= candle.open
          const color = up ? UP : DOWN
          const openY = y(candle.open)
          const closeY = y(candle.close)
          const top = Math.min(openY, closeY)
          const bodyH = Math.max(1.2, Math.abs(closeY - openY))
          return (
            <g key={index}>
              <line
                x1={x(index)}
                x2={x(index)}
                y1={y(candle.high)}
                y2={y(candle.low)}
                stroke={color}
                strokeWidth="1"
                opacity="0.8"
              />
              <rect x={x(index) - bodyW / 2} y={top} width={bodyW} height={bodyH} fill={color} rx="0.5" />
            </g>
          )
        })}

        <line
          x1={padL}
          x2={padL + innerW}
          y1={lastY}
          y2={lastY}
          stroke="#f7931a"
          strokeWidth="1"
          strokeDasharray="4 4"
          opacity="0.75"
        />
        <rect x={padL + innerW + 2} y={lastY - 9} width={64} height={18} rx="4" fill="#f7931a" />
        <text x={padL + innerW + 8} y={lastY + 4} fill="#120c03" fontSize="10.5" fontWeight="700" fontFamily="monospace">
          {money(last.close, 1)}
        </text>

        {candles.map((candle, index) =>
          index % labelEvery === 0 ? (
            <text
              key={`t-${index}`}
              x={x(index)}
              y={height - 6}
              fill="#5d6b7e"
              fontSize="10"
              textAnchor="middle"
              fontFamily="monospace"
            >
              {String(candle.time).slice(11, 16)}
            </text>
          ) : null,
        )}
      </svg>
    </div>
  )
}
