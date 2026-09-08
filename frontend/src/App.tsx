import { useState, useCallback, useRef, useEffect } from 'react'
import { flushSync } from 'react-dom'
import ChatView from './components/ChatView'
import InputBar from './components/InputBar'
import { createSession, type Session } from './api/client'
import { streamResume, SseCallbacks } from './api/sseClient'
import type { ChatMessage } from './components/ChatView'

import type { StreamState, ToolCallEvent } from './types'

interface LiveStream {
  sessionId: string
  assistantMsgId: string
  text: string
  reasoning: string
  toolCalls: ToolCallEvent[]
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

    // Kick off the graph immediately — fresh sessions have no history, so
    // passing an empty text lets the graph self-initialise and then pause at
    // its first interrupt (or finish if there is no user-input branch).
    const initId = `assistant-init-${nextId}`
    setNextId((n) => n + 1)

    let initState: StreamState = 'initializing'
    let initText = ''
    let initReasoning = ''
    let initToolCalls: ToolCallEvent[] = []
    setLiveStream({ sessionId: s.session_id, assistantMsgId: initId, text: '', reasoning: '', toolCalls: [], state: initState })

    const controller = streamResume(s.session_id, '', {
      onChunk: (type, content) => {
        if (type === 'answer') {
          initText += content
        } else {
          initReasoning += content
        }
        flushSync(() =>
          setLiveStream((prev) =>
            prev ? { ...prev, text: initText, reasoning: initReasoning } : prev,
          ),
        )
      },
      onToolCall: (call) => {
        initToolCalls = [...initToolCalls, call]
        flushSync(() =>
          setLiveStream((prev) =>
            prev ? { ...prev, toolCalls: initToolCalls } : prev,
          ),
        )
      },
      onInterrupt: () => {
        // Persist the initialization output as a message so it stays visible.
        setMessages((prev) => [...prev, { id: initId, role: 'assistant', text: initText, reasoning: initReasoning, toolCalls: initToolCalls }])
        setLiveStream(null)
      },
      onDone: () => {
        // Persist the initialization output as a message so it stays visible.
        setMessages((prev) => [...prev, { id: initId, role: 'assistant', text: initText, reasoning: initReasoning, toolCalls: initToolCalls }])
        setLiveStream(null)
      },
      onError: (detail) => {
        console.error('[App] init stream error:', detail)
        setLiveStream(null)
      },
      onComplete: () => {
        abortRef.current = null
      },
    })
    abortRef.current = controller
  }, [nextId])

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
    let accumulatedToolCalls: ToolCallEvent[] = []
    let state: StreamState = 'streaming'

    const callbacks: SseCallbacks = {
      onChunk: (type, content) => {
        if (type === 'answer') {
          accumulatedText += content
        } else {
          accumulatedReasoning += content
        }
        flushSync(() =>
          setLiveStream({ sessionId: session.session_id, assistantMsgId, text: accumulatedText, reasoning: accumulatedReasoning, toolCalls: accumulatedToolCalls, state }),
        )
      },
      onToolCall: (call) => {
        accumulatedToolCalls = [...accumulatedToolCalls, call]
        flushSync(() =>
          setLiveStream((prev) =>
            prev ? { ...prev, toolCalls: accumulatedToolCalls } : prev,
          ),
        )
      },
      onInterrupt: () => {
        state = 'interrupted'
        // Finalise the message with what we have so far
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMsgId
              ? { ...m, text: accumulatedText, reasoning: accumulatedReasoning, toolCalls: accumulatedToolCalls }
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
              ? { ...m, text: accumulatedText, reasoning: accumulatedReasoning, toolCalls: accumulatedToolCalls }
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
              ? { ...m, text: `⚠️ Ошибка:\n${detail}`, reasoning: '' }
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
            streamingToolCalls={liveStream?.toolCalls}
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
