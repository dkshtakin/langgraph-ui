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
  const [showMenu, setShowMenu] = useState(false)
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

  // Close dropdown when clicking outside.
  useEffect(() => {
    if (!showMenu || renaming) return
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setShowMenu(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [showMenu, renaming])

  const handleRenameSubmit = () => {
    const trimmed = editValue.trim()
    if (trimmed && trimmed !== session.title) {
      onRename(trimmed)
    } else {
      setEditValue(session.title)
    }
    setRenaming(false)
  }

  const toggleMenu = (e: React.MouseEvent) => {
    e.stopPropagation()
    setShowMenu((v) => !v)
  }

  return (
    <div
      className={`session-item${isActive ? ' session-item-active' : ''}`}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => {
        setHovered(false)
        setShowMenu(false)
      }}
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

      {/* Dots button — visible on hover, hidden while renaming */}
      {hovered && !renaming && (
        <button
          className="session-dots-btn"
          onClick={toggleMenu}
          title="Действия"
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" xmlns="http://www.w3.org/2000/svg">
            <circle cx="2" cy="8" r="1.5"/>
            <circle cx="8" cy="8" r="1.5"/>
            <circle cx="14" cy="8" r="1.5"/>
          </svg>
        </button>
      )}

      {/* Dropdown menu — shown only on click, hidden while renaming */}
      {showMenu && !renaming && (
        <div className="session-menu" ref={menuRef}>
          <button
            className="session-menu-btn"
            onClick={() => {
              setShowMenu(false)
              setRenaming(true)
            }}
            title="Переименовать"
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" xmlns="http://www.w3.org/2000/svg">
              <path d="M11.5 1.5a1.5 1.5 0 0 1 2.12 2.12l-9 9A1.5 1.5 0 0 1 3 13H2a1 1 0 0 1-1-1v-1a1.5 1.5 0 0 1 .44-1.06l9-9zM2 13h1m0-8L4 7M1 1l4 4"/>
            </svg>
            Переименовать
          </button>
          <button
            className="session-menu-btn session-menu-btn-danger"
            onClick={() => {
              setShowMenu(false)
              onDelete()
            }}
            title="Удалить"
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" xmlns="http://www.w3.org/2000/svg">
              <path d="M5.5 1h5a1 1 0 0 1 1 1v1h2v1H2V3h2V2a1 1 0 0 1 1-1zm1 4v7m2-7v7M3 5l1 9h8l1-9" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
              <path d="M6 5V3h4v2" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
            Удалить
          </button>
        </div>
      )}
    </div>
  )
}
