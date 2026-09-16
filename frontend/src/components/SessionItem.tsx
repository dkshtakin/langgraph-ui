import { useState, useRef, useEffect } from 'react'
import type { Session } from '../api/client'

interface SessionItemProps {
  session: Session
  isActive: boolean
  onClick: () => void
  onRename: (newTitle: string) => void
  onDelete: () => void
}

export default function SessionItem({
  session,
  isActive,
  onClick,
  onRename,
  onDelete,
}: SessionItemProps) {
  const [hovered, setHovered] = useState(false)
  const [renaming, setRenaming] = useState(false)
  const [editValue, setEditValue] = useState(session.title)
  const inputRef = useRef<HTMLInputElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (renaming) {
      inputRef.current?.focus()
      inputRef.current?.select()
    }
  }, [renaming])

  // Close the dropdown when clicking outside.
  useEffect(() => {
    if (!hovered || renaming) return
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setHovered(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [hovered, renaming])

  const handleRenameSubmit = () => {
    const trimmed = editValue.trim()
    if (trimmed && trimmed !== session.title) {
      onRename(trimmed)
    } else {
      setEditValue(session.title)
    }
    setRenaming(false)
  }

  return (
    <div
      className={`session-item${isActive ? ' session-item-active' : ''}`}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <button className="session-item-click" onClick={onClick}>
        {renaming ? (
          <input
            ref={inputRef}
            className="session-title-input"
            value={editValue}
            onChange={(e) => setEditValue(e.target.value)}
            onBlur={handleRenameSubmit}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleRenameSubmit()
              if (e.key === 'Escape') {
                setEditValue(session.title)
                setRenaming(false)
              }
            }}
          />
        ) : (
          <span className="session-title">{session.title}</span>
        )}
      </button>

      {hovered && !renaming && (
        <div className="session-menu" ref={menuRef}>
          <button
            className="session-menu-btn"
            onClick={() => setRenaming(true)}
            title="Переименовать"
          >
            Переименовать
          </button>
          <button
            className="session-menu-btn session-menu-btn-danger"
            onClick={onDelete}
            title="Удалить"
          >
            Удалить
          </button>
        </div>
      )}
    </div>
  )
}
