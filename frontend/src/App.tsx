import { useState, useCallback, useRef, useEffect } from 'react'
import { flushSync } from 'react-dom'
import ChatView from './components/ChatView'
import GraphSwitcher from './components/GraphSwitcher'
import InputBar from './components/InputBar'
import Sidebar from './components/Sidebar'
import { createSession, getGraphs, getMessages, getSessions, type GraphInfo, type SerializedMessage, type Session } from './api/client'
import { streamResume, SseCallbacks } from './api/sseClient'
import { appendChunk, appendToolCall, historyParts } from './messageStream'

import type { AssistantMessage, ChatMessage, StreamState } from './types'

interface LiveStream {
  sessionId: string
  messages: AssistantMessage[]
  state: StreamState
}

export default function App() {
  const [session, setSession] = useState<Session | null>(null)
  const [sessions, setSessions] = useState<Session[]>([])
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [nextId, setNextId] = useState(1)
  const [liveStream, setLiveStream] = useState<LiveStream | null>(null)
  const [graphs, setGraphs] = useState<GraphInfo[]>([])
  const [currentGraphId, setCurrentGraphId] = useState('book_planner')

  const abortRef = useRef<AbortController | null>(null)
  const liveIdRef = useRef(0)

  // Live messages need stable ids so React can reconcile them; they keep these
  // ids once the stream finalises and they join the feed.
  const nextLiveId = () => `live-${++liveIdRef.current}`

  // Load session list and graphs on mount.
  useEffect(() => {
    getSessions().then(setSessions).catch(console.error)
    getGraphs().then(setGraphs).catch(console.error)
  }, [])

  const refreshSessions = useCallback(async () => {
    try {
      const list = await getSessions()
      setSessions(list)
    } catch {
      // Silently ignore — the user can reload the page.
    }
  }, [])

  const switchSession = useCallback(async (sessionId: string | null) => {
    abortRef.current?.abort()
    abortRef.current = null
    setMessages([])
    setLiveStream(null)

    let nextSession: Session | null = sessionId ? sessions.find((s) => s.session_id === sessionId) ?? null : null
    if (nextSession) {
      try {
        const freshList = await getSessions()
        nextSession = freshList.find((s) => s.session_id === sessionId) ?? null
        setSessions(freshList)
      } catch {
        // Fallback to local list.
      }
    }
    setSession(nextSession)
    setCurrentGraphId(nextSession?.graph_id ?? 'book_planner')

    if (nextSession) {
      try {
        const raw = await getMessages(nextSession.session_id)
        // Tool results are not shown anywhere in the feed — drop them entirely.
        const mapped: ChatMessage[] = raw
          .filter((m) => m.role !== 'tool')
          .map((m, i): ChatMessage => {
            if (m.role === 'user' || m.role === 'system') {
              return { id: `msg-${i}`, role: m.role, text: m.text ?? '' }
            }
            return { id: `msg-${i}`, role: 'assistant', parts: historyParts(m) }
          })
        setMessages(mapped)
      } catch {
        console.error('[App] failed to load messages for session', nextSession.session_id)
      }
    }
  }, [sessions])

  const startNewSession = useCallback(async (graphId?: string) => {
    abortRef.current?.abort()
    abortRef.current = null
    setMessages([])
    setLiveStream(null)
    const s = await createSession(graphId ?? currentGraphId)
    setSession(s)
    setSessions((prev) => [s, ...prev])

    // Kick off the graph immediately — fresh sessions have no history, so
    // passing an empty text lets the graph self-initialise and then pause at
    // its first interrupt (or finish if there is no user-input branch).
    let initMessages: AssistantMessage[] = []
    setLiveStream({ sessionId: s.session_id, messages: [], state: 'initializing' })

    const pushInit = () => {
      flushSync(() => setLiveStream((prev) => (prev ? { ...prev, messages: initMessages } : prev)))
    }

    const controller = streamResume(s.session_id, '', {
      onChunk: (type, content) => {
        initMessages = appendChunk(initMessages, type === 'answer' ? 'text' : 'reasoning', content, nextLiveId())
        pushInit()
      },
      onToolCall: (call) => {
        initMessages = appendToolCall(initMessages, call, nextLiveId())
        pushInit()
      },
      onInterrupt: () => {
        // Persist the initialization output so it stays visible.
        setMessages((prev) => [...prev, ...initMessages])
        setLiveStream(null)
      },
      onDone: () => {
        // Persist the initialization output so it stays visible.
        setMessages((prev) => [...prev, ...initMessages])
        setLiveStream(null)
        getSessions().then((list) => {
          setSessions(list)
          if (session && list.find((s) => s.session_id === session.session_id)) {
            setSession(list.find((s) => s.session_id === session.session_id) ?? null)
          }
        }).catch(console.error)
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
  }, [currentGraphId])

  const handleSend = useCallback((message: string) => {
    if (!session) return

    setMessages((prev) => [...prev, { id: `user-${nextId}`, role: 'user', text: message }])
    setNextId((n) => n + 1)

    abortRef.current?.abort()
    abortRef.current = null

    let liveMessages: AssistantMessage[] = []
    let state: StreamState = 'streaming'

    const pushLive = () => {
      flushSync(() => setLiveStream({ sessionId: session.session_id, messages: liveMessages, state }))
    }

    const callbacks: SseCallbacks = {
      onChunk: (type, content) => {
        liveMessages = appendChunk(liveMessages, type === 'answer' ? 'text' : 'reasoning', content, nextLiveId())
        pushLive()
      },
      onToolCall: (call) => {
        liveMessages = appendToolCall(liveMessages, call, nextLiveId())
        pushLive()
      },
      onInterrupt: () => {
        state = 'interrupted'
        // The live messages join the feed as they are.
        setMessages((prev) => [...prev, ...liveMessages])
        setLiveStream(null)
      },
      onDone: () => {
        state = 'done'
        setMessages((prev) => [...prev, ...liveMessages])
        setLiveStream(null)
        getSessions().then((list) => {
          setSessions(list)
          if (session && list.find((s) => s.session_id === session.session_id)) {
            setSession(list.find((s) => s.session_id === session.session_id) ?? null)
          }
        }).catch(console.error)
      },
      onError: (detail) => {
        // Show the real error message so the user can understand what went wrong.
        console.error('[App] stream error:', detail, 'type:', typeof detail)
        state = 'idle'
        // The error replaces the turn's output, as it always has.
        setMessages((prev) => [
          ...prev,
          { id: nextLiveId(), role: 'assistant', parts: [{ kind: 'text', text: `⚠️ Ошибка:\n${detail}` }] },
        ])
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
      <Sidebar
        sessions={sessions}
        activeSessionId={session?.session_id ?? null}
        onSelect={(id) => switchSession(id || null)}
        onRefresh={refreshSessions}
      />

      <div className="main-wrapper">
        <div className="main-content">
          <header className="app-header">
            <GraphSwitcher
              currentGraphId={currentGraphId}
              sessionStatus={session?.status}
              streamState={liveStream?.state}
              graphs={graphs}
              onSelect={(id) => { setCurrentGraphId(id); startNewSession(id) }}
            />
          </header>

          {session ? (
            <>
              <ChatView
                messages={messages}
                streamingMessages={liveStream?.messages ?? []}
                streamState={liveStream?.state ?? 'idle'}
              />
              <InputBar
                streamState={liveStream?.state ?? 'idle'}
                disabled={session?.status === 'completed'}
                onSend={handleSend}
                onNewChat={startNewSession}
              />
            </>
          ) : (
            <div className="empty-state">
              <p>Start a new chat to begin.</p>
              <button className="new-chat-btn" onClick={() => startNewSession()}>
                New Chat
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
