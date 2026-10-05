import { useRef, useEffect } from 'react'
import MessageBlock from './MessageBlock'
import type { AssistantMessage, ChatMessage, StreamState } from '../types'

interface ChatViewProps {
  messages: ChatMessage[]
  streamingMessages: AssistantMessage[]
  streamState: StreamState
}

/* Насколько близко к низу ещё считается, что мы «следуем» за лентой. Выше —
   значит пользователь ушёл читать историю, и автоскролл надо отпустить. */
const STICK_TO_BOTTOM_PX = 40

export default function ChatView({ messages, streamingMessages, streamState }: ChatViewProps) {
  const bottomRef = useRef<HTMLDivElement>(null)
  const scrollerRef = useRef<HTMLElement | null>(null)
  const stickyRef = useRef(true)

  /* Прокручивается не эта лента, а контейнер выше (.main-wrapper в App).
     Находим его один раз и следим за позицией: уход наверх снимает автоскролл,
     возврат к низу снова его включает. */
  useEffect(() => {
    const scroller = bottomRef.current?.closest<HTMLElement>('.main-wrapper') ?? null
    scrollerRef.current = scroller
    if (!scroller) return

    const onScroll = () => {
      const fromBottom = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight
      stickyRef.current = fromBottom <= STICK_TO_BOTTOM_PX
    }
    onScroll()
    scroller.addEventListener('scroll', onScroll, { passive: true })
    return () => scroller.removeEventListener('scroll', onScroll)
  }, [])

  /* Смена сессии подменяет всю ленту — к ней снова прилипаем, независимо от
     того, где пользователь был в предыдущей. */
  const firstMessageId = messages[0]?.id ?? null
  useEffect(() => {
    stickyRef.current = true
  }, [firstMessageId])

  useEffect(() => {
    const scroller = scrollerRef.current
    if (!scroller || !stickyRef.current) return
    scroller.scrollTop = scroller.scrollHeight
  }, [messages, streamingMessages])

  const hasLiveStream = streamState === 'streaming' || streamState === 'interrupted' || streamState === 'initializing'

  return (
    <div className="chat-view">
      <div className="messages-list">
        {messages.map((msg) => (
          <MessageBlock key={msg.id} {...msg} />
        ))}

        {/* Live assistant messages — same renderer, plus the flag that drives
            the auto-expanding trailing row. */}
        {hasLiveStream && streamingMessages.map((msg) => (
          <MessageBlock key={msg.id} {...msg} isLive />
        ))}

        <div ref={bottomRef} />
      </div>
    </div>
  )
}
