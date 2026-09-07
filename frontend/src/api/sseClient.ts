/**
 * SSE client for the /api/resume/{session_id} endpoint.
 *
 * Emits typed events from the backend's SSE stream:
 *   - answer      — text chunk belonging to the model's final answer
 *   - reasoning   — text chunk inside a <|channel>thought…<channel|> block
 *   - interrupt   — graph paused, awaiting user input  (data.reason)
 *   - done        — graph finished normally             (data: {})
 *   - error       — server-side error                   (data.detail)
 */

export type SseEventType = 'answer' | 'reasoning' | 'interrupt' | 'done' | 'error'

interface SseEvent {
  event: SseEventType | 'data'
  data: Record<string, unknown>
}

export interface SseCallbacks {
  onChunk?: (type: 'answer' | 'reasoning', content: string) => void
  onInterrupt?: (reason: string) => void
  onDone?: () => void
  onError?: (detail: string) => void
  onComplete?: () => void   // fires after done or error, stream is closed
}

function parseSseLine(line: string): SseEvent | null {
  if (!line.trim()) return null
  const colonIdx = line.indexOf(':')
  if (colonIdx === -1) return null
  const key = line.slice(0, colonIdx).trim()
  const value = line.slice(colonIdx + 1).trim()

  if (key === 'event') {
    return { event: value as SseEventType, data: {} }
  }
  if (key === 'data' && value) {
    try {
      return { event: 'data', data: JSON.parse(value) }
    } catch {
      return { event: 'data', data: {} }
    }
  }
  return null
}

export function streamResume(
  sessionId: string,
  userMessage: string,
  callbacks: SseCallbacks,
): AbortController {
  const controller = new AbortController()

  fetch(`/api/resume/${encodeURIComponent(sessionId)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text: userMessage }),
    signal: controller.signal,
  })
    .then(async (response) => {
      const reader = response.body?.getReader()
      if (!reader) {
        callbacks.onError?.('No response body')
        callbacks.onComplete?.()
        return
      }

      const decoder = new TextDecoder()
      let buffer = ''

      try {
        // eslint-disable-next-line no-constant-condition
        while (true) {
          if (controller.signal.aborted) break

          const { done, value } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })

          // Process complete SSE messages
          const lines = buffer.split('\n')
          // Keep the last possibly-incomplete line in the buffer
          buffer = lines.pop() ?? ''

          for (const line of lines) {
            const parsed = parseSseLine(line)
            if (!parsed) continue

            if (parsed.event === 'answer' || parsed.event === 'reasoning') {
              const content = (parsed.data as any)?.content as string | undefined
              if (content !== undefined) {
                callbacks.onChunk?.(parsed.event, content)
              }
            } else if (parsed.event === 'interrupt') {
              const reason = (parsed.data as any)?.reason as string || 'unknown'
              callbacks.onInterrupt?.(reason)
            } else if (parsed.event === 'done') {
              callbacks.onDone?.()
            } else if (parsed.event === 'error') {
              const detail = (parsed.data as any)?.detail as string || 'Unknown error'
              callbacks.onError?.(detail)
            }
          }
        }
      } finally {
        callbacks.onComplete?.()
        reader.releaseLock()
      }
    })
    .catch((err: unknown) => {
      if ((err as { name?: string }).name !== 'AbortError') {
        const detail = (err as { message?: string }).message ?? String(err)
        callbacks.onError?.(detail)
      }
      callbacks.onComplete?.()
    })

  return controller
}
