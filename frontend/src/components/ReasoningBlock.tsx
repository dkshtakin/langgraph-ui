import { useState } from 'react'
import { Sparkles } from 'lucide-react'
import CollapsibleRow from './CollapsibleRow'

interface ReasoningBlockProps {
  text: string
  /** True while this part is the last one of a message that is still streaming. */
  isTrailing: boolean
}

export default function ReasoningBlock({ text, isTrailing }: ReasoningBlockProps) {
  // null until the user clicks; from then on their choice wins over the auto
  // rule, so the row never closes under a user who just opened it.
  const [manual, setManual] = useState<boolean | null>(null)
  const expanded = manual ?? isTrailing

  return (
    <CollapsibleRow
      icon={<Sparkles size={15} strokeWidth={1.8} aria-hidden="true" />}
      label="Reasoning"
      expanded={expanded}
      onToggle={() => setManual(!expanded)}
    >
      <div className="row-text">{text}</div>
    </CollapsibleRow>
  )
}
