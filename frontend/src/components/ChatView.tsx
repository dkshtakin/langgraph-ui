import { useRef, useEffect } from 'react'
import MessageBlock from './MessageBlock'
import type { StreamState } from '../types'

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  text: string
  reasoning?: string
}

interface ChatViewProps {
  messages: ChatMessage[]
  streamingText: string
  reasoningText: string
  streamState: StreamState
}

export default function ChatView({ messages, streamingText, reasoningText, streamState }: ChatViewProps) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamingText, reasoningText])

  const hasLiveStream = streamState === 'streaming' || streamState === 'interrupted' || streamState === 'initializing'

  return (
    <div className="chat-view">
      <div className="messages-list">
        {messages.map((msg) => (
          <MessageBlock key={msg.id} role={msg.role} text={msg.text} reasoning={msg.reasoning} />
        ))}

        {/* Live streaming assistant message */}
        {(hasLiveStream && (streamingText || reasoningText)) && (
          <div className="msg-assistant live-stream">
            {reasoningText && (
              <details className="reasoning-block" open={true}>
                <summary className="reasoning-summary">Reasoning</summary>
                <div className="reasoning-content" dangerouslySetInnerHTML={{ __html: formatMarkdown(reasoningText) }} />
              </details>
            )}
            {streamingText && (
              <div className="msg-bubble answer-bubble" dangerouslySetInnerHTML={{ __html: formatMarkdown(streamingText) }} />
            )}
          </div>
        )}

        <div ref={bottomRef} />
      </div>
    </div>
  )
}

function formatMarkdown(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .split('\n').join('<br />')
}
