import { ToolCallList } from './ToolCallBlock'
import type { ToolCallEvent } from '../types'

interface MessageBlockProps {
  role: 'user' | 'assistant' | 'system'
  text: string
  reasoning?: string
  toolCalls?: ToolCallEvent[]
}

export default function MessageBlock({ role, text, reasoning, toolCalls }: MessageBlockProps) {
  if (role === 'user') {
    return (
      <div className="msg-user">
        <div className="msg-bubble user-bubble">{text}</div>
      </div>
    )
  }

  if (role === 'system') {
    return (
      <div className="msg-system">
        <div className="msg-bubble system-bubble" dangerouslySetInnerHTML={{ __html: formatMarkdown(text || '') }} />
      </div>
    )
  }

  const isError = text.startsWith('⚠️ Ошибка:')

  return (
    <div className="msg-assistant">
      {reasoning && (
        <details className="reasoning-block" open={true}>
          <summary className="reasoning-summary">Reasoning</summary>
          <div className="reasoning-content" dangerouslySetInnerHTML={{ __html: formatMarkdown(reasoning) }} />
        </details>
      )}
      {toolCalls && toolCalls.length > 0 && (
        <ToolCallList calls={toolCalls} />
      )}
      {text && (
        <div
          className={`msg-bubble ${isError ? 'error-bubble' : 'answer-bubble'}`}
          dangerouslySetInnerHTML={{ __html: formatMarkdown(text) }}
        />
      )}
    </div>
  )
}

/**
 * Minimal markdown formatting — newlines to <br>, basic safety.
 */
function formatMarkdown(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .split('\n').join('<br />')
}
