export type StreamState = 'idle' | 'initializing' | 'streaming' | 'interrupted' | 'done'

export interface ToolCallEvent {
  name: string
  args: Record<string, unknown>
  invalid?: boolean  // true when emitted as "invalid_tool_call"
}
