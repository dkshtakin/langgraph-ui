import { useState, useRef, useEffect } from 'react'
import { Ellipsis, Pencil, Trash2 } from 'lucide-react'
import { threadTitle } from '../thread'
import type { Thread } from '../api/agentServer'

interface ThreadItemProps {
  thread: Thread
  isActive: boolean
  onClick: () => void
  onRename: (newTitle: string) => void
  onDelete: () => void
}

export default function ThreadItem({
  thread,
  isActive,
  onClick,
  onRename,
  onDelete,
}: ThreadItemProps) {
  const title = threadTitle(thread)
  const [hovered, setHovered] = useState(false)
  const [showMenu, setShowMenu] = useState(false)
  const [renaming, setRenaming] = useState(false)
  const [editValue, setEditValue] = useState(title)
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
    if (trimmed && trimmed !== title) {
      onRename(trimmed)
    } else {
      setEditValue(title)
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
                setEditValue(title)
                setRenaming(false)
              }
            }}
          />
        ) : (
          <span className="session-title">{title}</span>
        )}
      </button>

      {/* Dots button — visible on hover, hidden while renaming */}
      {hovered && !renaming && (
        <button
          className="session-dots-btn"
          onClick={toggleMenu}
          title="Действия"
        >
          <Ellipsis size={16} strokeWidth={2} aria-hidden="true" />
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
            <Pencil size={16} strokeWidth={2} aria-hidden="true" />
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
            <Trash2 size={16} strokeWidth={2} aria-hidden="true" />
            Удалить
          </button>
        </div>
      )}
    </div>
  )
}
