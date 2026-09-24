import { useState } from 'react'
import { stringifyArgs } from '../toolArgs'
import type { ToolCallEvent } from '../types'

interface ToolCallBlockProps {
  call: ToolCallEvent
}

function ToolCallBlock({ call }: ToolCallBlockProps) {
  const [collapsed, setCollapsed] = useState(true)
  const args = stringifyArgs(call.args)

  return (
    <div className={`tool-call-block ${call.invalid ? 'tool-call-invalid' : 'tool-call-valid'}`}>
      <div className="tool-call-header" onClick={() => setCollapsed((c) => !c)}>
        <span className="tool-call-name">{call.name}</span>
        {call.invalid && <span className="tool-call-badge invalid">invalid</span>}
      </div>
      <div className={`tool-call-content-wrap ${collapsed ? 'collapsed' : ''}`}>
        <div className="tool-call-content">
          <div className="tool-call-args-label">Аргументы</div>
          {args
            ? <pre className="tool-call-args"><code>{args}</code></pre>
            : <div className="tool-call-no-args">нет аргументов</div>}
        </div>
      </div>
    </div>
  )
}

interface ToolCallListProps {
  calls: ToolCallEvent[]
}

export function ToolCallList({ calls }: ToolCallListProps) {
  return (
    <div className="tool-call-list">
      {calls.map((call, i) => (
        <ToolCallBlock key={i} call={call} />
      ))}
    </div>
  )
}
