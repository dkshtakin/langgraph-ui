import { useState, KeyboardEvent, useEffect, useRef } from 'react'
import type { StreamState } from '../types'

interface InputBarProps {
  streamState: StreamState
  onSend: (message: string) => void
  onNewChat: () => void
}

export default function InputBar({ streamState, onSend, onNewChat }: InputBarProps) {
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

  const isStreaming = streamState === 'streaming'
  const isInterrupted = streamState === 'interrupted'
  const isDone = streamState === 'done'

  let placeholder = 'Введите сообщение…'
  if (isInterrupted) placeholder = 'Введите ваш ответ…'
  else if (isStreaming) placeholder = 'Ответ генерируется…'

  return (
    <div className="input-bar">
      {isDone && (
        <button className="new-chat-btn" onClick={onNewChat}>
          New Chat
        </button>
      )}
      <div className="input-row">
        <input
          ref={inputRef}
          type="text"
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={isStreaming}
          className="chat-input"
        />
        <button
          className="send-btn"
          onClick={handleSubmit}
          disabled={isStreaming || !inputValue.trim()}
          title="Send"
        >
          Send
        </button>
      </div>
    </div>
  )
}
