import { useState, useCallback, useEffect } from 'react'
import SessionItem from './SessionItem'
import { renameSession, deleteSession, type Session } from '../api/client'

const COLLAPSED_STORAGE_KEY = 'sidebar-collapsed'

interface SidebarProps {
  sessions: Session[]
  activeSessionId: string | null
  onSelect: (sessionId: string) => void
  onRefresh: () => void
}

export default function Sidebar({ sessions, activeSessionId, onSelect, onRefresh }: SidebarProps) {
  // Read synchronously so the first paint is already in the right state — no
  // collapse animation when the page loads.
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem(COLLAPSED_STORAGE_KEY) === 'true')

  useEffect(() => {
    localStorage.setItem(COLLAPSED_STORAGE_KEY, String(collapsed))
  }, [collapsed])

  const handleRename = useCallback(
    async (sessionId: string, newTitle: string) => {
      try {
        await renameSession(sessionId, newTitle)
      } catch {
        // Optimistic update already applied; server failure is silently ignored.
      }
    },
    [],
  )

  const handleDelete = useCallback(
    async (sessionId: string) => {
      try {
        await deleteSession(sessionId)
      } catch {
        // If the active session was deleted, App will fall back gracefully.
      }
      onRefresh()
      if (activeSessionId === sessionId) {
        onSelect('')
      }
    },
    [activeSessionId, onSelect, onRefresh],
  )

  const toggleLabel = collapsed ? 'Развернуть' : 'Свернуть'

  return (
    <aside
      className={`sidebar${collapsed ? ' sidebar-collapsed' : ''}`}
      // While collapsed the column is the only click target, so any click on it
      // expands the panel.
      onClick={collapsed ? () => setCollapsed(false) : undefined}
    >
      <div className="sidebar-header">
        <h2 className="sidebar-title">Запущенные графы</h2>
        <button
          className="sidebar-toggle"
          onClick={(e) => {
            e.stopPropagation()
            setCollapsed((v) => !v)
          }}
          title={toggleLabel}
          aria-label={toggleLabel}
          aria-expanded={!collapsed}
        >
          <svg
            width="16"
            height="16"
            viewBox="0 0 16 16"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
            xmlns="http://www.w3.org/2000/svg"
          >
            <rect x="1.75" y="2.75" width="12.5" height="10.5" rx="2.5" />
            <path d="M6.25 2.75v10.5" />
          </svg>
        </button>
      </div>

      <div className="sidebar-content">
        {sessions.length === 0 ? (
          <p className="sidebar-empty">Нет сессий</p>
        ) : (
          <div className="session-list">
            {sessions.map((s) => (
              <SessionItem
                key={s.session_id}
                session={s}
                isActive={s.session_id === activeSessionId}
                onClick={() => onSelect(s.session_id)}
                onRename={(title) => handleRename(s.session_id, title)}
                onDelete={() => handleDelete(s.session_id)}
              />
            ))}
          </div>
        )}
      </div>
    </aside>
  )
}
