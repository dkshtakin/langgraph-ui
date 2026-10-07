import { useEffect, useMemo, useRef } from 'react'
import { useMessages, useStream } from '@langchain/react'
import { API_URL } from '../api/agentServer'
import ChatView from './ChatView'
import InputBar from './InputBar'
import { describe, log, logError } from '../log'
import { toFeed } from '../messageParts'
import { streamStateOf } from '../streamState'
import type { ChatMessage, StreamState } from '../types'

interface ChatPaneProps {
  /** The graph this thread runs, taken from the thread itself. */
  assistantId: string
  threadId: string
  /** True for a thread created moments ago, whose opening run is still owed. */
  startRun: boolean
  onRunStarted: () => void
  /** The header shows the state of the open thread, and it lives up there. */
  onState: (state: StreamState, failed: boolean) => void
}

export default function ChatPane({
  assistantId,
  threadId,
  startRun,
  onRunStarted,
  onState,
}: ChatPaneProps) {
  const stream = useStream({ assistantId, apiUrl: API_URL, threadId })
  const messages = useMessages(stream)

  const feed = useMemo(() => {
    const mapped = toFeed(messages)
    if (stream.error == null) return mapped

    // A failed run carries no answer, so the failure takes its place in the
    // feed — the same inline shape errors have always had.
    const failure: ChatMessage = {
      id: 'stream-error',
      role: 'assistant',
      parts: [{ kind: 'text', text: `⚠️ Ошибка:\n${describe(stream.error)}` }],
    }
    return [...mapped, failure]
  }, [messages, stream.error])

  const state = streamStateOf({
    isLoading: stream.isLoading,
    isThreadLoading: stream.isThreadLoading,
    hasMessages: messages.length > 0,
    interrupts: stream.interrupts.length,
  })

  const failed = stream.error != null
  useEffect(() => {
    onState(state, failed)
  }, [state, failed, onState])

  // What the pane asked for, and what it has to show for it. Logged on every
  // change of shape rather than every render: a thread that stays at zero
  // messages after a reload is exactly the case this is here to reveal.
  useEffect(() => {
    log(`thread ${threadId} on "${assistantId}": opening`)
  }, [threadId, assistantId])

  useEffect(() => {
    if (stream.isThreadLoading) {
      log(`thread ${threadId}: loading history…`)
      return
    }
    log(
      `thread ${threadId}: ${messages.length} message(s), ` +
        `${stream.interrupts.length} interrupt(s), ${stream.isLoading ? 'running' : state}`,
    )
  }, [threadId, stream.isThreadLoading, stream.isLoading, messages.length, stream.interrupts.length, state])

  useEffect(() => {
    if (stream.error == null) return
    logError(`thread ${threadId}: the stream failed —`, describe(stream.error))
  }, [threadId, stream.error])

  // Leaving detaches the client without cancelling the run, which is what lets
  // a thread come back with the answer written while the user was elsewhere.
  // The ref is refreshed after the render that replaced the stream, never during it.
  const streamRef = useRef(stream)
  useEffect(() => {
    streamRef.current = stream
  }, [stream])
  useEffect(() => () => void streamRef.current.disconnect(), [])

  // One instance now follows many threads, so the opening run is remembered per
  // thread rather than once for the life of the component.
  const startedFor = useRef<string | null>(null)
  useEffect(() => {
    if (!startRun || startedFor.current === threadId) return
    startedFor.current = threadId
    // An empty input is the opening move: the graph initialises itself and
    // stops at its first interrupt, or runs to the end if it has no such stop.
    log(`thread ${threadId}: starting the opening run with an empty input`)
    void stream.submit({})
    onRunStarted()
  }, [startRun, threadId, stream, onRunStarted])

  const handleSend = (text: string) => {
    const human = { type: 'human', content: text }
    const pending = stream.interrupts[0]

    // Waiting on the user — the text is the resume value and the message joins
    // the state in the same step, exactly as the old resume endpoint did. The
    // interrupt is named rather than left to the hook to find: just after a
    // reload the hook knows a thread is parked but not yet where, and an
    // unnamed resume is refused.
    if (pending) {
      log(`thread ${threadId}: resuming interrupt ${pending.id} with a ${text.length}-character message`)
      void stream.respond(text, { interruptId: pending.id, update: { messages: [human] } })
      return
    }

    // Running to completion — nothing to resume, so this is an ordinary turn.
    log(`thread ${threadId}: no interrupt pending, sending as a new run`)
    void stream.submit({ messages: [human] })
  }

  return (
    <>
      <ChatView messages={feed} live={state === 'streaming' || state === 'initializing'} />
      <InputBar
        streamState={state}
        disabled={state === 'done'}
        onSend={handleSend}
      />
    </>
  )
}
