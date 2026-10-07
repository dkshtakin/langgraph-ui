/**
 * The UI's own view of what a thread is doing.
 *
 * The server reports `idle` / `busy` / `interrupted` / `error`; the components
 * switch on a five-value vocabulary of their own, which drives the status dot,
 * the input placeholder and whether the input is usable at all. This is the
 * only place the two meet.
 */

import type { StreamState } from './types'

export interface StreamSignals {
  /** A run is active on this thread — streaming, or about to be. */
  isLoading: boolean
  /** The thread's state is still being fetched, so nothing is known yet. */
  isThreadLoading: boolean
  hasMessages: boolean
  /** How many unresolved interrupts the thread is parked on. */
  interrupts: number
}

export function streamStateOf({
  isLoading,
  isThreadLoading,
  hasMessages,
  interrupts,
}: StreamSignals): StreamState {
  // Hydration is lumped in with starting a run: both mean "not ready yet", and
  // the input has to stay shut either way — an interrupt that has not arrived
  // yet would send the next message down the wrong path.
  if (isLoading || isThreadLoading) return hasMessages ? 'streaming' : 'initializing'

  if (interrupts > 0) return 'interrupted'

  return hasMessages ? 'done' : 'idle'
}

/**
 * The status dot beside the graph name. A failed thread is the one state the
 * dot reports on its own: the feed itself stays a feed, so the error has
 * nowhere else to show up.
 */
export function dotClass(state: StreamState, failed: boolean): string {
  if (failed) return 'dot-error'
  if (state === 'streaming' || state === 'initializing') return 'dot-streaming'
  if (state === 'interrupted') return 'dot-paused'
  if (state === 'done') return 'dot-completed'
  return 'dot-idle'
}
