/**
 * Rendering tool call arguments.
 *
 * Three shapes reach us. A valid call carries a parsed object, both live and
 * from history. An invalid one carries the raw string its JSON failed to
 * parse, or null when it carried no arguments at all. All three have to render
 * — an empty string means "no arguments".
 */

import type { ToolCallArgs } from './types'

export function stringifyArgs(args: ToolCallArgs | undefined): string {
  if (args === null || args === undefined) return ''
  // A string here already failed to parse upstream — showing it verbatim is
  // the only honest thing left, and a second parse attempt would fail again.
  if (typeof args === 'string') return args
  if (Object.keys(args).length === 0) return ''
  return JSON.stringify(args, null, 2)
}
