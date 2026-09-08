import type { ToolCallEvent } from '../types'

/** Minimal JSON pretty-print for tool call args. */
export function stringifyArgs(args: Record<string, unknown>): string {
  if (Object.keys(args).length === 0) return ''
  try {
    return JSON.stringify(args, null, 2)
  } catch {
    return String(args)
  }
}

interface ToolCallListProps {
  calls: ToolCallEvent[]
}

export function ToolCallList({ calls }: ToolCallListProps) {
  return (
    <div className="tool-call-list">
      {calls.map((call, i) => (
        <div key={i} className={`tool-call-block ${call.invalid ? 'tool-call-invalid' : 'tool-call-valid'}`}>
          <div className="tool-call-header">
            <span className="tool-call-name">{call.name}</span>
            {call.invalid && <span className="tool-call-badge invalid">invalid</span>}
          </div>
          {stringifyArgs(call.args) && (
            <pre className="tool-call-args"><code>{stringifyArgs(call.args)}</code></pre>
          )}
        </div>
      ))}
    </div>
  )
}
