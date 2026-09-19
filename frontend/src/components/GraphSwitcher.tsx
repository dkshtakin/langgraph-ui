import { useState, useRef, useEffect } from 'react'
import type { GraphInfo } from '../api/client'

interface Props {
  currentGraphId: string
  sessionStatus?: string
  streamState?: 'idle' | 'initializing' | 'streaming' | 'interrupted' | 'done'
  graphs: GraphInfo[]
  onSelect: (graphId: string) => void
}

export default function GraphSwitcher({ currentGraphId, sessionStatus, streamState, graphs, onSelect }: Props) {
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  const currentGraph = graphs.find((g) => g.id === currentGraphId)
  const isStreaming = streamState === 'streaming' || streamState === 'initializing'
  const isPaused = sessionStatus === 'paused'
  const isCompleted = sessionStatus === 'completed'

  useEffect(() => {
    if (!open) return
    function handler(e: MouseEvent) {
      if (!containerRef.current?.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  return (
    <div ref={containerRef} className="graph-switcher">
      <button
        className="graph-switcher-btn"
        onClick={() => setOpen((v) => !v)}
      >
        <span className="graph-switcher-label">{currentGraph?.name ?? currentGraphId}</span>
        <span className={`graph-switcher-dot ${isStreaming ? 'dot-streaming' : isPaused ? 'dot-paused' : isCompleted ? 'dot-completed' : 'dot-idle'}`} />
      </button>

      {open && (
        <div className="graph-switcher-dropdown">
          {graphs.map((g) => (
            <button
              key={g.id}
              className={`graph-switcher-item${g.id === currentGraphId ? ' graph-switcher-item-active' : ''}`}
              onClick={() => { onSelect(g.id); setOpen(false) }}
            >
              {g.name}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
