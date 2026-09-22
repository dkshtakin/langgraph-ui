export type StreamState = 'idle' | 'initializing' | 'streaming' | 'interrupted' | 'done'

export interface ToolCallEvent {
  name: string
  args: Record<string, unknown>
  invalid?: boolean  // true when emitted as "invalid_tool_call"
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
