import { useState, useCallback, useEffect } from 'react'
import { PanelLeft, RefreshCw, Search, Settings } from 'lucide-react'
import SessionItem from './SessionItem'
import { renameSession, deleteSession, type Session } from '../api/client'

const COLLAPSED_STORAGE_KEY = 'sidebar-collapsed'

interface SidebarProps {
  sessions: Session[]
  activeSessionId: string | null
  onSelect: (sessionId: string) => void
  onRefresh: () => void
  onReloadGraphs: () => void
  reloadingGraphs: boolean
}

export default function Sidebar({
  sessions,
  activeSessionId,
  onSelect,
  onRefresh,
  onReloadGraphs,
  reloadingGraphs,
}: SidebarProps) {
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
        <h2 className="sidebar-title sidebar-brand">langgraph-ui</h2>
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
          <PanelLeft size={16} strokeWidth={2} aria-hidden="true" />
        </button>
      </div>

      <div className="sidebar-actions">
        <button
          className="sidebar-action"
          onClick={(e) => {
            // Collapsed, the whole column expands the panel on click.
            e.stopPropagation()
            onReloadGraphs()
          }}
          disabled={reloadingGraphs}
          title="Перезагрузить графы"
          aria-label="Перезагрузить графы"
        >
          <span className={`sidebar-action-icon${reloadingGraphs ? ' sidebar-action-icon-spinning' : ''}`}>
            <RefreshCw size={16} strokeWidth={2} aria-hidden="true" />
          </span>
          <span className="sidebar-action-label">Перезагрузить</span>
        </button>

        <button
          className="sidebar-action"
          onClick={(e) => {
            e.stopPropagation()
          }}
          title="Поиск"
          aria-label="Поиск"
        >
          <span className="sidebar-action-icon">
            <Search size={16} strokeWidth={2} aria-hidden="true" />
          </span>
          <span className="sidebar-action-label">Поиск</span>
        </button>

        <button
          className="sidebar-action"
          onClick={(e) => {
            e.stopPropagation()
          }}
          title="Настройки"
          aria-label="Настройки"
        >
          <span className="sidebar-action-icon">
            <Settings size={16} strokeWidth={2} aria-hidden="true" />
          </span>
          <span className="sidebar-action-label">Настройки</span>
        </button>
      </div>

      <h2 className="sidebar-title sidebar-section-title">Запущенные графы</h2>

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
