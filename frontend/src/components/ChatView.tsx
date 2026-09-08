import { useRef, useEffect } from 'react'
import MessageBlock from './MessageBlock'
import { ToolCallList } from './ToolCallBlock'
import type { StreamState, ToolCallEvent } from '../types'

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  text: string
  reasoning?: string
  toolCalls?: ToolCallEvent[]
}

interface ChatViewProps {
  messages: ChatMessage[]
  streamingText: string
  reasoningText: string
  streamingToolCalls?: ToolCallEvent[]
  streamState: StreamState
}

export default function ChatView({ messages, streamingText, reasoningText, streamingToolCalls, streamState }: ChatViewProps) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamingText, reasoningText])

  const hasLiveStream = streamState === 'streaming' || streamState === 'interrupted' || streamState === 'initializing'

  return (
    <div className="chat-view">
      <div className="messages-list">
        {messages.map((msg) => (
          <MessageBlock key={msg.id} role={msg.role} text={msg.text} reasoning={msg.reasoning} toolCalls={msg.toolCalls} />
        ))}

        {/* Live streaming assistant message */}
        {(hasLiveStream && (streamingText || reasoningText || streamingToolCalls?.length)) && (
          <div className="msg-assistant live-stream">
            {reasoningText && (
              <details className="reasoning-block" open={true}>
                <summary className="reasoning-summary">Reasoning</summary>
                <div className="reasoning-content" dangerouslySetInnerHTML={{ __html: formatMarkdown(reasoningText) }} />
              </details>
            )}
            {streamingToolCalls && streamingToolCalls.length > 0 && (
              <ToolCallList calls={streamingToolCalls} />
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
