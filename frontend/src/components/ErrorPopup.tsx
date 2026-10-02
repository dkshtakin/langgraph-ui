interface Props {
  lines: string[]
  onClose: () => void
}

/**
 * Bottom-right error box. Stays until dismissed — no auto-hide, an error the
 * user never read is worse than a box they have to close.
 */
export default function ErrorPopup({ lines, onClose }: Props) {
  if (lines.length === 0) return null

  return (
    <div className="error-popup" role="alert" onClick={onClose}>
      <button
        className="error-popup-close"
        onClick={(e) => {
          // The box itself closes on click; the cross is only a target.
          e.stopPropagation()
          onClose()
        }}
        aria-label="Закрыть"
      >
        ×
      </button>
      {lines.map((line, i) => (
        <p className="error-popup-line" key={i}>
          {line}
        </p>
      ))}
    </div>
  )
}
