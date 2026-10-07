import { useState, useRef, useEffect } from 'react'
import { dotClass } from '../streamState'
import type { StreamState } from '../types'

interface Props {
  currentGraphId: string
  streamState: StreamState
  /** The thread the dot is reporting on is in the server's `error` state. */
  failed?: boolean
  graphs: string[]
  onSelect: (graphId: string) => void
}

export default function GraphSwitcher({ currentGraphId, streamState, failed, graphs, onSelect }: Props) {
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

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
        {/* The graph id is the name: `langgraph.json` keys are already readable. */}
        <span className="graph-switcher-label">{currentGraphId}</span>
        <span className={`graph-switcher-dot ${dotClass(streamState, !!failed)}`} />
      </button>

      {open && (
        <div className="graph-switcher-dropdown">
          {graphs.map((id) => (
            <button
              key={id}
              className={`graph-switcher-item${id === currentGraphId ? ' graph-switcher-item-active' : ''}`}
              onClick={() => { onSelect(id); setOpen(false) }}
            >
              {id}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
