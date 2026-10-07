export type StreamState = 'idle' | 'initializing' | 'streaming' | 'interrupted' | 'done'

/**
 * A valid call carries its parsed arguments; an invalid one carries the raw
 * string that failed to parse, or null when it had no arguments at all.
 */
export type ToolCallArgs = Record<string, unknown> | string | null

/** What the agent server knows about a run that produced this call. */
export type ToolCallStatus = 'pending' | 'completed' | 'error'

export interface ToolCallResult {
  status: ToolCallStatus
  /** The tool's output, or the text of the failure. Empty while pending. */
  text: string
}

export interface ToolCallEvent {
  /** The server's id for the call, used to find its outcome. */
  id?: string
  name: string
  args: ToolCallArgs
  invalid?: boolean  // the call never parsed, so it never ran
  /** Absent when nothing is known about the call yet. */
  result?: ToolCallResult
}

/**
 * One ordered piece of an assistant message. Parts arrive in the order the
 * graph produced them: reasoning → tool calls → answer.
 */
export type MessagePart =
  | { kind: 'reasoning'; text: string }
  | { kind: 'tool_calls'; calls: ToolCallEvent[] }
  | { kind: 'text'; text: string }

export interface AssistantMessage {
  id: string
  role: 'assistant'
  parts: MessagePart[]
}

export interface PlainMessage {
  id: string
  role: 'user' | 'system'
  text: string
}

export type ChatMessage = AssistantMessage | PlainMessage
