interface MessageBlockProps {
  role: 'user' | 'assistant'
  text: string
  reasoning?: string
}

export default function MessageBlock({ role, text, reasoning }: MessageBlockProps) {
  if (role === 'user') {
    return (
      <div className="msg-user">
        <div className="msg-bubble user-bubble">{text}</div>
      </div>
    )
  }

  return (
    <div className="msg-assistant">
      {reasoning && (
        <details className="reasoning-block" open={true}>
          <summary className="reasoning-summary">Reasoning</summary>
          <div className="reasoning-content" dangerouslySetInnerHTML={{ __html: formatMarkdown(reasoning) }} />
        </details>
      )}
      {text && <div className="msg-bubble answer-bubble" dangerouslySetInnerHTML={{ __html: formatMarkdown(text) }} />}
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
