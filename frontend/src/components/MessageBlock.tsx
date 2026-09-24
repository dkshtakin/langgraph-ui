import { ToolCallList } from './ToolCallBlock'
import ReasoningBlock from './ReasoningBlock'
import Markdown from './Markdown'
import type { ChatMessage, MessagePart } from '../types'

export default function MessageBlock(message: ChatMessage) {
  if ('parts' in message) {
    return (
      <div className="msg-assistant">
        {message.parts.map((part, i) => (
          <Part key={i} part={part} />
        ))}
      </div>
    )
  }

  if (message.role === 'system') {
    return (
      <div className="msg-system">
        <div className="msg-bubble system-bubble">{message.text}</div>
      </div>
    )
  }

  return (
    <div className="msg-user">
      <div className="msg-bubble user-bubble">{message.text}</div>
    </div>
  )
}

function Part({ part }: { part: MessagePart }) {
  if (part.kind === 'reasoning') {
    return <ReasoningBlock text={part.text} />
  }

  if (part.kind === 'tool_calls') {
    return <ToolCallList calls={part.calls} />
  }

  // Whitespace-only answers are a backend artefact — a message that only called
  // a tool carries "\n\n" as its text, which would render as an empty bubble.
  if (!part.text.trim()) {
    return null
  }

  const isError = part.text.startsWith('⚠️ Ошибка:')

  return (
    <div className={`msg-bubble ${isError ? 'error-bubble' : 'answer-bubble'}`}>
      {isError ? part.text : <Markdown text={part.text} />}
    </div>
  )
}
