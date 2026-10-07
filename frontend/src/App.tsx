import { useState, useCallback, useRef, useEffect } from 'react'
import ChatPane from './components/ChatPane'
import ErrorPopup from './components/ErrorPopup'
import GraphSwitcher from './components/GraphSwitcher'
import Sidebar from './components/Sidebar'
import {
  createThread,
  deleteThread,
  listGraphs,
  listThreads,
  renameThread,
  type Thread,
} from './api/agentServer'
import { defaultTitle, graphIdOf } from './thread'
import { describe, log, logError } from './log'
import type { StreamState } from './types'

/** Survives a reload that lost the query parameter. */
const ACTIVE_THREAD_KEY = 'active-thread'

/** The thread the address points at, if it points at one. */
function readThreadParam(): string | null {
  return new URLSearchParams(window.location.search).get('thread')
}

/**
 * Keep the address in step with the open thread. The parameter is the durable
 * record of where the user is: it survives a reload, and the thread list in the
 * sidebar is what makes the id meaningful again after a restart.
 */
function writeThreadParam(threadId: string | null, push: boolean) {
  const url = new URL(window.location.href)
  if (threadId) url.searchParams.set('thread', threadId)
  else url.searchParams.delete('thread')

  const next = `${url.pathname}${url.search}`
  if (push) window.history.pushState({}, '', next)
  else window.history.replaceState({}, '', next)
}

function initialThreadId(): string | null {
  const fromUrl = readThreadParam()
  const fromStorage = sessionStorage.getItem(ACTIVE_THREAD_KEY)
  const where = fromUrl ? `?thread=${fromUrl}` : 'no ?thread in the address'
  const fallback = !fromUrl && fromStorage ? ` — falling back to the stored ${fromStorage}` : ''
  log(`boot: ${where}${fallback}`)
  return fromUrl ?? fromStorage
}

export default function App() {
  const [threads, setThreads] = useState<Thread[]>([])
  const [graphs, setGraphs] = useState<string[]>([])
  // The graph the next new chat will run. An open thread's own graph wins over
  // this for as long as it is open.
  const [graphId, setGraphId] = useState('')
  const [threadId, setThreadId] = useState<string | null>(initialThreadId)
  /** Set once a thread list has actually arrived, so an empty list is not mistaken for a missing thread. */
  const [threadsLoaded, setThreadsLoaded] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [errors, setErrors] = useState<string[]>([])
  /** A thread created moments ago whose opening run is still owed. */
  const [startPending, setStartPending] = useState<string | null>(null)
  /** Reported up by the open pane, which is where the stream actually lives. */
  const [streamState, setStreamState] = useState<StreamState>('idle')
  const [streamFailed, setStreamFailed] = useState(false)
  const creatingRef = useRef(false)

  const activeThread = threads.find((t) => t.thread_id === threadId) ?? null
  const missing = threadsLoaded && threadId !== null && !activeThread
  const currentGraphId = activeThread ? graphIdOf(activeThread) : graphId

  /** Add a failure to the error box, under the name of what was being asked of the server. */
  const reportError = useCallback((label: string, err: unknown) => {
    setErrors((prev) => [...prev, `${label}: ${describe(err)}`])
  }, [])

  // Which thread the address ended up pointing at, and whether the list knows
  // it yet. A thread that never resolves is the "empty chat" case.
  useEffect(() => {
    if (threadId === null) {
      log('no thread open')
    } else if (activeThread) {
      log(`open thread ${threadId} on graph "${graphIdOf(activeThread)}"`)
    } else if (missing) {
      logError(`thread ${threadId} is not in the list the server returned — showing "not found"`)
    } else {
      log(`thread ${threadId} is waiting for the thread list`)
    }
  }, [threadId, activeThread, missing])

  // Load the sidebar and the dropdown once, on mount.
  useEffect(() => {
    let cancelled = false

    listThreads()
      .then((list) => {
        if (cancelled) return
        setThreads(list)
        setThreadsLoaded(true)
      })
      .catch((err) => {
        if (!cancelled) reportError('Треды', err)
      })

    listGraphs()
      .then((list) => {
        if (cancelled) return
        setGraphs(list)
        setGraphId((current) => current || list[0] || '')
      })
      .catch((err) => {
        if (!cancelled) reportError('Графы', err)
      })

    return () => {
      cancelled = true
    }
  }, [reportError])

  const applyThread = useCallback((id: string | null) => {
    setThreadId(id)
    setStreamState('idle')
    setStreamFailed(false)
  }, [])

  // The address never changes without this running, so storage cannot drift.
  useEffect(() => {
    if (threadId) sessionStorage.setItem(ACTIVE_THREAD_KEY, threadId)
    else sessionStorage.removeItem(ACTIVE_THREAD_KEY)
  }, [threadId])

  const openThread = useCallback(
    (id: string | null) => {
      applyThread(id)
      writeThreadParam(id, true)
    },
    [applyThread],
  )

  // Back and forward walk the threads the user has opened.
  useEffect(() => {
    const onPop = () => applyThread(readThreadParam())
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [applyThread])

  const refresh = useCallback(async () => {
    setRefreshing(true)
    try {
      setThreads(await listThreads())
      setThreadsLoaded(true)
    } catch (err) {
      reportError('Треды', err)
    } finally {
      setRefreshing(false)
    }
  }, [reportError])

  /**
   * Switching graph means a new thread: a thread is bound to its assistant for
   * life, so there is nothing to reconfigure. The old thread is let go of
   * before the new one exists, so a failed create never leaves the address
   * pointing at a thread of the previous graph.
   */
  const startNewChat = useCallback(
    async (graph: string) => {
      if (creatingRef.current) return
      creatingRef.current = true

      applyThread(null)
      writeThreadParam(null, false)
      setGraphId(graph)

      try {
        const created = await createThread(graph, defaultTitle(graph, Date.now()))
        setThreads((prev) => [created, ...prev])
        setStartPending(created.thread_id)
        applyThread(created.thread_id)
        writeThreadParam(created.thread_id, true)
      } catch (err) {
        reportError('Не удалось создать тред', err)
      } finally {
        creatingRef.current = false
      }
    },
    [applyThread, reportError],
  )

  const handleRename = useCallback(
    async (id: string, title: string) => {
      // The row shows the new name at once; the server is told in parallel.
      setThreads((prev) =>
        prev.map((t) => (t.thread_id === id ? { ...t, metadata: { ...t.metadata, title } } : t)),
      )
      try {
        await renameThread(id, title)
      } catch (err) {
        reportError('Не удалось переименовать', err)
      }
    },
    [reportError],
  )

  const handleDelete = useCallback(
    async (id: string) => {
      try {
        await deleteThread(id)
      } catch (err) {
        // The thread is still on the server, so its row stays where it is.
        reportError('Не удалось удалить', err)
        return
      }
      setThreads((prev) => prev.filter((t) => t.thread_id !== id))
      if (id === threadId) openThread(null)
    },
    [threadId, openThread, reportError],
  )

  const handleRunStarted = useCallback(() => setStartPending(null), [])
  const handleStreamState = useCallback((state: StreamState, failed: boolean) => {
    setStreamState(state)
    setStreamFailed(failed)
  }, [])

  return (
    <div className="app-layout">
      <Sidebar
        threads={threads}
        activeThreadId={threadId}
        onSelect={openThread}
        onRefresh={refresh}
        refreshing={refreshing}
        onRename={handleRename}
        onDelete={handleDelete}
      />

      <div className="main-wrapper">
        <div className="main-content">
          <header className="app-header">
            <GraphSwitcher
              currentGraphId={currentGraphId}
              streamState={streamState}
              failed={streamFailed || activeThread?.status === 'error'}
              graphs={graphs}
              onSelect={startNewChat}
            />
          </header>

          {activeThread ? (
            <ChatPane
              // Rebuilt only when the graph changes: the hook binds a graph for
              // the lifetime of the instance, but it follows a `threadId` prop
              // on its own. Remounting per thread instead would leave the old
              // thread's event streams open, and a browser only allows a
              // handful of connections to one origin.
              key={graphIdOf(activeThread)}
              assistantId={graphIdOf(activeThread)}
              threadId={activeThread.thread_id}
              startRun={startPending === activeThread.thread_id}
              onRunStarted={handleRunStarted}
              onState={handleStreamState}
            />
          ) : missing ? (
            // The id stays in the address: it is what the user asked for, and
            // it stays copyable while they decide what to do about it.
            <div className="empty-state">
              <p>Тред не найден</p>
            </div>
          ) : threadsLoaded ? (
            <div className="empty-state">
              <p>Start a new chat to begin.</p>
              <button className="new-chat-btn" onClick={() => startNewChat(currentGraphId)}>
                New Chat
              </button>
            </div>
          ) : null}
        </div>
      </div>

      <ErrorPopup lines={errors} onClose={() => setErrors([])} />
    </div>
  )
}
