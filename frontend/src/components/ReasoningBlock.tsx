import { useState } from 'react'
import { formatMarkdown } from '../markdown'

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
