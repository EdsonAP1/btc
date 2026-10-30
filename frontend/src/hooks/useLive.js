import { useEffect, useRef, useState } from 'react'
import { getStatus } from '../api.js'

/**
 * Mantiene el estado del bot en vivo.
 * Usa WebSocket y, además, polling cada 5 s como red de seguridad.
 */
export function useLive() {
  const [status, setStatus] = useState(null)
  const [connected, setConnected] = useState(false)
  const [events, setEvents] = useState([])
  const [error, setError] = useState(null)
  const mounted = useRef(true)

  useEffect(() => {
    mounted.current = true
    let socket = null
    let retry = 0
    let reconnectTimer = null
    let closedByUs = false

    const pushEvent = (evt) => {
      setEvents((prev) => [evt, ...prev].slice(0, 60))
    }

    const connect = () => {
      if (closedByUs || !mounted.current) return
      const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
      const url = `${proto}://${window.location.host}/api/ws`
      try {
        socket = new WebSocket(url)
      } catch {
        scheduleReconnect()
        return
      }
      socket.onopen = () => {
        retry = 0
        setConnected(true)
        setError(null)
      }
      socket.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data)
          if (msg.type === 'status') {
            setStatus(msg.data)
          } else if (msg.type === 'log') {
            setStatus((prev) => (prev ? { ...prev, logs: [...(prev.logs || []).slice(-29), msg.data] } : prev))
          } else {
            pushEvent(msg)
          }
        } catch {
          /* mensaje inválido */
        }
      }
      socket.onerror = () => socket?.close()
      socket.onclose = () => {
        setConnected(false)
        scheduleReconnect()
      }
    }

    const scheduleReconnect = () => {
      if (closedByUs || !mounted.current) return
      const delay = Math.min(1000 * 2 ** retry, 10000)
      retry += 1
      clearTimeout(reconnectTimer)
      reconnectTimer = setTimeout(connect, delay)
    }

    const poll = async () => {
      try {
        const data = await getStatus()
        if (mounted.current) {
          setStatus(data)
          setError(null)
        }
      } catch (err) {
        if (mounted.current) setError(err.message)
      }
    }

    connect()
    poll()
    const interval = setInterval(poll, 5000)

    return () => {
      mounted.current = false
      closedByUs = true
      clearInterval(interval)
      clearTimeout(reconnectTimer)
      socket?.close()
    }
  }, [])

  return { status, connected, events, error, refresh: () => getStatus().then(setStatus) }
}
