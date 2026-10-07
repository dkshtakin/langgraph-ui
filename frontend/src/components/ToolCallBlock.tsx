import { useState } from 'react'
import { Wrench } from 'lucide-react'
import { stringifyArgs } from '../toolArgs'
import CollapsibleRow from './CollapsibleRow'
import type { ToolCallEvent } from '../types'

interface ToolCallBlockProps {
  call: ToolCallEvent
}

/** What the tool answered, under the arguments that were asked with. */
function Result({ call }: ToolCallBlockProps) {
  if (!call.result) return null

  return (
    <>
      <div className="row-args-label">Результат</div>
      {call.result.status === 'pending'
        ? <div className="row-no-args">выполняется</div>
        : <pre className="row-args"><code>{call.result.text}</code></pre>}
    </>
  )
}

function ToolCallBlock({ call }: ToolCallBlockProps) {
  const [expanded, setExpanded] = useState(false)
  const args = stringifyArgs(call.args)

  return (
    <CollapsibleRow
      icon={<Wrench size={15} strokeWidth={1.8} aria-hidden="true" />}
      label={<>Инструмент <span className="row-tool-name">{call.name}</span></>}
      badge={call.invalid && <span className="tool-call-badge invalid">invalid</span>}
      expanded={expanded}
      onToggle={() => setExpanded((e) => !e)}
    >
      {args
        ? <>
            <div className="row-args-label">Аргументы</div>
            <pre className="row-args"><code>{args}</code></pre>
          </>
        : <div className="row-no-args">нет аргументов</div>}
      <Result call={call} />
    </CollapsibleRow>
  )
}

interface ToolCallListProps {
  calls: ToolCallEvent[]
}

/** Строки вызовов — прямые соседи остальных строк сообщения: так зазор между
 *  ними задаётся одним правилом `.row + .row`, без промежуточной обёртки. */
export function ToolCallList({ calls }: ToolCallListProps) {
  return (
    <>
      {calls.map((call, i) => (
        <ToolCallBlock key={call.id ?? i} call={call} />
      ))}
    </>
  )
}
