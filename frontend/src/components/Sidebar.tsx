import { useState, useCallback } from 'react'
import SessionItem from './SessionItem'
import { renameSession, deleteSession, type Session } from '../api/client'

interface SidebarProps {
  sessions: Session[]
  activeSessionId: string | null
  onSelect: (sessionId: string) => void
  onRefresh: () => void
}

export default function Sidebar({ sessions, activeSessionId, onSelect, onRefresh }: SidebarProps) {
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

  if (sessions.length === 0) {
    return (
      <aside className="sidebar">
        <h2 className="sidebar-title">Запущенные графы</h2>
        <p className="sidebar-empty">Нет сессий</p>
      </aside>
    )
  }

  return (
    <aside className="sidebar">
      <h2 className="sidebar-title">Запущенные графы</h2>
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
    </aside>
  )
}
