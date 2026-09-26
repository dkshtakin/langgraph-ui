import { ChevronRight } from 'lucide-react'
import type { ReactNode } from 'react'

/**
 * Общий хром строк reasoning и вызовов инструментов: кнопка с иконкой,
 * подписью, необязательным бейджем и шевроном, плюс раскрывающееся содержимое.
 */

interface CollapsibleRowProps {
  icon: ReactNode
  label: ReactNode
  badge?: ReactNode
  expanded: boolean
  onToggle: () => void
  children: ReactNode
}

export default function CollapsibleRow({
  icon,
  label,
  badge,
  expanded,
  onToggle,
  children,
}: CollapsibleRowProps) {
  return (
    <div className={`row ${expanded ? 'row-expanded' : 'row-collapsed'}`}>
      <button
        type="button"
        className="row-btn"
        aria-expanded={expanded}
        onClick={onToggle}
      >
        <span className="row-icon">{icon}</span>
        <span className="row-label">{label}</span>
        {badge}
        <span className="row-chevron">
          <ChevronRight size={12} strokeWidth={2.5} aria-hidden="true" />
        </span>
      </button>
      <div className="row-content-wrap">
        <div className="row-content">{children}</div>
      </div>
    </div>
  )
}
