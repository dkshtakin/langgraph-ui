import { ToolCallList } from './ToolCallBlock'
import ReasoningBlock from './ReasoningBlock'
import Markdown from './Markdown'
import type { ChatMessage, MessagePart } from '../types'

export default function MessageBlock(message: ChatMessage & { isLive?: boolean }) {
  if ('parts' in message) {
    const { parts, isLive } = message
    return (
      <div className="msg-assistant">
        {parts.map((part, i) => (
          <Part key={i} part={part} isTrailing={!!isLive && i === parts.length - 1} />
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

function Part({ part, isTrailing }: { part: MessagePart; isTrailing: boolean }) {
  if (part.kind === 'reasoning') {
    // Whitespace-only reasoning is the same backend artefact as the blank text
    // below — it would render as a row that opens onto nothing. The model also
    // wraps its reasoning in newlines (`<think>\n…`), which pre-wrap would show
    // as an empty first line.
    const text = part.text.trim()
    if (!text) {
      return null
    }
    return <ReasoningBlock text={text} isTrailing={isTrailing} />
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
