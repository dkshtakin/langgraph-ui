import { useState } from 'react'

interface ReasoningBlockProps {
  text: string
}

export default function ReasoningBlock({ text }: ReasoningBlockProps) {
  const [collapsed, setCollapsed] = useState(false)

  return (
    <div className="reasoning-block">
      <summary
        className="reasoning-summary"
        onClick={() => setCollapsed((c) => !c)}
      >
        Reasoning
      </summary>
      <div className={`reasoning-content-wrap ${collapsed ? 'collapsed' : ''}`}>
        <div className="reasoning-content" dangerouslySetInnerHTML={{ __html: formatMarkdown(text) }} />
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
