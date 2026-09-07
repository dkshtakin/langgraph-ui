import { useState, useCallback, useRef, useEffect } from 'react'
import ChatView from './components/ChatView'
import InputBar from './components/InputBar'
import { createSession, type Session } from './api/client'
import { streamResume, SseCallbacks } from './api/sseClient'
import type { ChatMessage } from './components/ChatView'

import type { StreamState } from './types'

interface LiveStream {
  sessionId: string
  assistantMsgId: string
  text: string
  reasoning: string
  state: StreamState
}

export default function App() {
  const [session, setSession] = useState<Session | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [nextId, setNextId] = useState(1)
  const [liveStream, setLiveStream] = useState<LiveStream | null>(null)

  const abortRef = useRef<AbortController | null>(null)

  const startNewSession = useCallback(async () => {
    abortRef.current?.abort()
    abortRef.current = null
    setMessages([])
    setLiveStream(null)
    const s = await createSession('book_planner')
    setSession(s)
  }, [])

  const handleSend = useCallback((message: string) => {
    if (!session) return

    const assistantMsgId = `assistant-${nextId}`
    setNextId((n) => n + 1)

    setMessages((prev) => [
      ...prev,
      { id: `user-${nextId}`, role: 'user', text: message },
      { id: assistantMsgId, role: 'assistant', text: '', reasoning: '' },
    ])
    setNextId((n) => n + 1)

    abortRef.current?.abort()
    abortRef.current = null

    let accumulatedText = ''
    let accumulatedReasoning = ''
    let state: StreamState = 'streaming'

    const callbacks: SseCallbacks = {
      onChunk: (type, content) => {
        if (type === 'answer') {
          accumulatedText += content
        } else {
          accumulatedReasoning += content
        }
        setLiveStream({ sessionId: session.session_id, assistantMsgId, text: accumulatedText, reasoning: accumulatedReasoning, state })
      },
      onInterrupt: () => {
        state = 'interrupted'
        // Finalise the message with what we have so far
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMsgId
              ? { ...m, text: accumulatedText, reasoning: accumulatedReasoning }
              : m,
          ),
        )
        setLiveStream(null)
      },
      onDone: () => {
        state = 'done'
        // Finalise the message
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMsgId
              ? { ...m, text: accumulatedText, reasoning: accumulatedReasoning }
              : m,
          ),
        )
        setLiveStream(null)
      },
      onError: (detail) => {
        // Show the real error message so the user can understand what went wrong.
        console.error('[App] stream error:', detail, 'type:', typeof detail)
        state = 'idle'
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMsgId
              ? { ...m, text: `⚠️ Ошибка: ${detail}`.slice(0, 500), reasoning: '' }
              : m,
          ),
        )
        setLiveStream(null)
      },
      onComplete: () => {
        abortRef.current = null
      },
    }

    const controller = streamResume(session.session_id, message, callbacks)
    abortRef.current = controller
  }, [session, nextId])

  // Abort on unmount
  useEffect(() => {
    return () => {
      abortRef.current?.abort()
    }
  }, [])

  return (
    <div className="app-layout">
      <header className="app-header">
        <h1>Book Planner</h1>
        {!session && (
          <button className="new-chat-btn" onClick={startNewSession}>
            New Chat
          </button>
        )}
      </header>

      {session ? (
        <>
          <ChatView
            messages={messages}
            streamingText={liveStream?.text ?? ''}
            reasoningText={liveStream?.reasoning ?? ''}
            streamState={liveStream?.state ?? 'idle'}
          />
          <InputBar
            streamState={liveStream?.state ?? 'idle'}
            onSend={handleSend}
            onNewChat={startNewSession}
          />
        </>
      ) : (
        <div className="empty-state">
          <p>Start a new chat to begin.</p>
          <button className="new-chat-btn" onClick={startNewSession}>
            New Chat
          </button>
        </div>
      )}
    </div>
  )
}
