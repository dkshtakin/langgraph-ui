import { useState, useEffect } from 'react'
import { PanelLeft, RefreshCw, Search, Settings } from 'lucide-react'
import ThreadItem from './ThreadItem'
import type { Thread } from '../api/agentServer'

const COLLAPSED_STORAGE_KEY = 'sidebar-collapsed'

interface SidebarProps {
  threads: Thread[]
  activeThreadId: string | null
  onSelect: (threadId: string | null) => void
  onRefresh: () => void
  refreshing: boolean
  onRename: (threadId: string, title: string) => void
  onDelete: (threadId: string) => void
}

export default function Sidebar({
  threads,
  activeThreadId,
  onSelect,
  onRefresh,
  refreshing,
  onRename,
  onDelete,
}: SidebarProps) {
  // Read synchronously so the first paint is already in the right state — no
  // collapse animation when the page loads.
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem(COLLAPSED_STORAGE_KEY) === 'true')

  useEffect(() => {
    localStorage.setItem(COLLAPSED_STORAGE_KEY, String(collapsed))
  }, [collapsed])

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
            onRefresh()
          }}
          disabled={refreshing}
          title="Перезагрузить графы"
          aria-label="Перезагрузить графы"
        >
          <span className={`sidebar-action-icon${refreshing ? ' sidebar-action-icon-spinning' : ''}`}>
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
        {threads.length === 0 ? (
          <p className="sidebar-empty">Нет сессий</p>
        ) : (
          <div className="session-list">
            {threads.map((t) => (
              <ThreadItem
                key={t.thread_id}
                thread={t}
                isActive={t.thread_id === activeThreadId}
                onClick={() => onSelect(t.thread_id)}
                onRename={(title) => onRename(t.thread_id, title)}
                onDelete={() => onDelete(t.thread_id)}
              />
            ))}
          </div>
        )}
      </div>
    </aside>
  )
}
