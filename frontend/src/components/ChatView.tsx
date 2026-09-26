import { useRef, useEffect } from 'react'
import MessageBlock from './MessageBlock'
import type { AssistantMessage, ChatMessage, StreamState } from '../types'

interface ChatViewProps {
  messages: ChatMessage[]
  streamingMessages: AssistantMessage[]
  streamState: StreamState
}

export default function ChatView({ messages, streamingMessages, streamState }: ChatViewProps) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
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
