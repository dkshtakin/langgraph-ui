/**
 * SSE client for the /api/resume/{session_id} endpoint.
 *
 * Emits typed events from the backend's SSE stream:
 *   - answer      — text chunk belonging to the model's final answer
 *   - reasoning   — text chunk inside a end_reasoning_tag...end_reasoning_tag block
 *   - interrupt   — graph paused, awaiting user input  (data.reason)
 *   - done        — graph finished normally             (data: {})
 *   - error       — server-side error                   (data.detail)
 */

import type { ToolCallArgs } from '../types'

export type SseEventType = 'answer' | 'reasoning' | 'interrupt' | 'done' | 'error' | 'tool_call' | 'invalid_tool_call'

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
  /** Emitted when the LLM invokes a tool. `invalid=true` means the call was rejected by the server. */
  onToolCall?: (call: { name: string; args: ToolCallArgs; invalid: boolean }) => void
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
      if (!response.ok) {
        const ct = response.headers.get('content-type') || ''
        let errorText = `HTTP ${response.status} ${response.statusText}`
        try {
          const json = await response.json() as Record<string, unknown>
          errorText += ` — ${(json.detail as string | undefined) ?? JSON.stringify(json)}`
        } catch {
          // plain-text body — nothing to extract
        }
        console.error('[sseClient] non-OK response:', response.status, errorText)
        callbacks.onError?.(errorText)
        callbacks.onComplete?.()
        return
      }

      const reader = response.body?.getReader()
      if (!reader) {
        callbacks.onError?.('No response body')
        callbacks.onComplete?.()
        return
      }

      const decoder = new TextDecoder()
      let buffer = ''
      // SSE sends "event:" and "data:" on separate lines; track the current
      // event type so the following data line is merged into the same message.
      let pendingEventType: 'answer' | 'reasoning' | 'interrupt' | 'done' | 'error' | 'tool_call' | 'invalid_tool_call' | null = null

      try {
        // eslint-disable-next-line no-constant-condition
        while (true) {
          if (controller.signal.aborted) break

          let chunk: string
          try {
            const result = await reader.read()
            if (result.done) break
            chunk = decoder.decode(result.value, { stream: true })
          } catch (readErr) {
            // Broken pipe / connection reset — surface to the client
            console.error('[sseClient] read failed:', readErr)
            callbacks.onError?.(String(readErr))
            callbacks.onComplete?.()
            return
          }

          buffer += chunk

          // Process complete SSE messages
          const lines = buffer.split('\n')
          // Keep the last possibly-incomplete line in the buffer
          buffer = lines.pop() ?? ''

          for (const line of lines) {
            const parsed = parseSseLine(line)
            if (!parsed) continue

            try {
              // "event: answer/reasoning/tool_call/invalid_tool_call" — stash type and wait for the data line
              if (parsed.event === 'answer' || parsed.event === 'reasoning' || parsed.event === 'tool_call' || parsed.event === 'invalid_tool_call') {
                pendingEventType = parsed.event
                continue
              }

              // Terminal events are emitted as "event: X" followed by "data: {...}"
              // on separate lines; stash the type and wait for the data line.
              if (parsed.event === 'interrupt' || parsed.event === 'done' || parsed.event === 'error') {
                pendingEventType = parsed.event
                continue
              }

              // "data:" line without a preceding "event:" — ignore
              if (parsed.event === 'data' && pendingEventType === null) {
                continue
              }

              // "data:" line completing a pending answer/reasoning/error/interrupt/done event
              if (parsed.event === 'data' && pendingEventType !== null) {
                const eventType = pendingEventType
                pendingEventType = null

                if (eventType === 'answer' || eventType === 'reasoning') {
                  const content = (parsed.data as any)?.content as string | undefined
                  if (content !== undefined) {
                    // console.log('[sseClient] chunk:', eventType, content.slice(0, 50))
                    callbacks.onChunk?.(eventType, content)
                  }
                } else if (eventType === 'tool_call' || eventType === 'invalid_tool_call') {
                  const name = (parsed.data as any)?.name as string | undefined
                  // Keep null as null — an invalid call with no arguments is a
                  // real case, and `?? {}` would hide it from the renderer.
                  const args = ((parsed.data as any)?.args ?? null) as ToolCallArgs
                  if (name) {
                    console.log('[sseClient] tool_call:', eventType, name)
                    callbacks.onToolCall?.({ name, args, invalid: eventType === 'invalid_tool_call' })
                  }
                } else if (eventType === 'interrupt') {
                  const reason = (parsed.data as any)?.reason as string || 'unknown'
                  console.log('[sseClient] interrupt:', reason)
                  callbacks.onInterrupt?.(reason)
                } else if (eventType === 'done') {
                  console.log('[sseClient] done')
                  callbacks.onDone?.()
                } else if (eventType === 'error') {
                  const detail = (parsed.data as any)?.detail as string | undefined
                  console.log('[sseClient] error event received, detail:', detail?.slice(0, 800))
                  callbacks.onError?.(detail ?? 'Generation failed — see console for details')
                }
              }
            } catch (cbErr) {
              console.error('[sseClient] callback threw:', cbErr)
            }
          }
        }
      } finally {
        callbacks.onComplete?.()
        reader.releaseLock()
      }
    })
    .catch((err: unknown) => {
      const name = (err as { name?: string }).name
      if (name === 'AbortError') return // user-initiated cancel, not an error

      const detail = (err as { message?: string }).message ?? String(err)
      console.error('[sseClient] fetch threw:', err)
      callbacks.onError?.(detail)
      callbacks.onComplete?.()
    })

  return controller
}
