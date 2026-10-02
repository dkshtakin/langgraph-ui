import { useState, KeyboardEvent, useEffect, useRef } from 'react'
import { ArrowUp } from 'lucide-react'
import type { StreamState } from '../types'

interface InputBarProps {
  streamState: StreamState
  disabled?: boolean
  onSend: (message: string) => void
  onNewChat: () => void
}

export default function InputBar({ streamState, disabled, onSend, onNewChat }: InputBarProps) {
  const [inputValue, setInputValue] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (streamState === 'interrupted') {
      inputRef.current?.focus()
    }
  }, [streamState])

  const handleSubmit = () => {
    const msg = inputValue.trim()
    if (!msg) return
    onSend(msg)
    setInputValue('')
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  const isInitializing = streamState === 'initializing'
  const isStreaming = streamState === 'streaming'
  const isInterrupted = streamState === 'interrupted'
  const isDone = streamState === 'done'

  let placeholder = 'Введите сообщение'
  if (isInterrupted) placeholder = 'Введите ваш ответ'
  else if (isStreaming || isInitializing) placeholder = 'Запуск графа'

  const sendable = !disabled && !isStreaming && !isInitializing && inputValue.trim().length > 0

  return (
    <div className="input-bar">
      {isDone && (
        <button className="new-chat-btn" onClick={onNewChat}>
          New Chat
        </button>
      )}
      <div className="input-wrapper">
        <input
          ref={inputRef}
          type="text"
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled || isStreaming || isInitializing}
          className="chat-input"
        />
        <button
          className={`send-btn${sendable ? ' send-btn-active' : ''}`}
          onClick={handleSubmit}
          disabled={!sendable}
          title="Send"
        >
          <ArrowUp size={16} strokeWidth={2.5} aria-hidden="true" />
        </button>
      </div>
    </div>
  )
}
