/**
 * Console trace of what the app loads and what fails.
 *
 * Three things arrive from the agent server on their own schedule: the thread
 * list, the history of the open thread, and the stream that extends it. When
 * one of them does not arrive, the screen looks exactly like a thread that
 * simply has nothing in it — an empty chat with no visible reason. Every step
 * that asks the server for something says so here, and says what came back,
 * so an empty screen has an explanation in the console.
 */

const PREFIX = '[ui]'

/** Error text for a value that may not be an `Error`. */
export function describe(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}

export function log(...parts: unknown[]): void {
  console.log(PREFIX, ...parts)
}

export function logError(...parts: unknown[]): void {
  console.error(PREFIX, ...parts)
}
