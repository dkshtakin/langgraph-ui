/**
 * Turning the agent server's state into the feed the UI renders.
 *
 * The server hands back LangChain messages; the components want an ordered list
 * of `ChatMessage`. That mapping lives here, on its own, so the render layer
 * never sees a server object and this file never sees a component.
 */

import type {
  ChatMessage,
  MessagePart,
  ToolCallArgs,
  ToolCallEvent,
  ToolCallResult,
} from './types'

/** The fields we read off a LangChain message. */
export interface AgentMessage {
  id?: string
  type?: string
  content?: unknown
  /** Provider fields on the message — where the reasoning rides. */
  additional_kwargs?: Record<string, unknown>
  tool_calls?: RawToolCall[]
  invalid_tool_calls?: RawToolCall[]
  /** On a tool message: the call it answers. */
  tool_call_id?: string
  /** On a tool message: `success` | `error`. */
  status?: string
}

export interface RawToolCall {
  id?: string
  name?: string
  args?: unknown
}

/**
 * Text of a message whose content is a string or a list of content blocks.
 *
 * Only text blocks contribute. A block of another kind carries its own `text`
 * or `reasoning` key, and reading it would glue something that is not the
 * answer into the answer.
 */
function textOf(content: unknown): string {
  if (typeof content === 'string') return content
  if (!Array.isArray(content)) return ''

  return content
    .map((block) => {
      if (typeof block === 'string') return block
      if (typeof block !== 'object' || block === null) return ''
      const { type, text } = block as { type?: unknown; text?: unknown }
      if (type !== undefined && type !== 'text') return ''
      return typeof text === 'string' ? text : ''
    })
    .join('')
}

/** Render a tool's return value, whatever shape it came back in. */
function renderResult(output: unknown): string {
  if (output === null || output === undefined) return ''
  if (typeof output === 'string') return output
  return JSON.stringify(output, null, 2)
}

/**
 * What every call the thread has already answered came back with, by call id.
 *
 * The tool message is the only place the outcome exists: the SDK's `toolCalls`
 * projection is filled in while a run streams and is empty for a thread read
 * back from the server, so a result taken from it would vanish on reload.
 */
function resultsById(messages: AgentMessage[]): Map<string, ToolCallResult> {
  const results = new Map<string, ToolCallResult>()

  for (const message of messages) {
    if (message.type !== 'tool' || !message.tool_call_id) continue
    results.set(message.tool_call_id, {
      status: message.status === 'error' ? 'error' : 'completed',
      text: renderResult(message.content),
    })
  }

  return results
}

/** Calls of one message, in the order the model asked for them. */
function ownCalls(message: AgentMessage): ToolCallEvent[] {
  const valid: ToolCallEvent[] = (message.tool_calls ?? []).map((call) => ({
    id: call.id,
    name: call.name ?? '',
    args: (call.args as ToolCallArgs) ?? null,
  }))

  // An invalid call never parsed, so its args stay the raw string that failed.
  const invalid: ToolCallEvent[] = (message.invalid_tool_calls ?? []).map((call) => ({
    id: call.id,
    name: call.name ?? '',
    args: (call.args as ToolCallArgs) ?? null,
    invalid: true,
  }))

  return [...valid, ...invalid]
}

/** Attach the outcome of a call, when the thread has one for it. */
function withOutcome(call: ToolCallEvent, results: Map<string, ToolCallResult>): ToolCallEvent {
  if (call.id === undefined) return call
  const result = results.get(call.id)
  return result ? { ...call, result } : call
}

/** Reasoning a message carries as a content block, in the standard shape. */
function reasoningInBlocks(content: unknown): string {
  if (!Array.isArray(content)) return ''

  return content
    .map((block) => {
      if (typeof block !== 'object' || block === null) return ''
      const { type, reasoning } = block as { type?: unknown; reasoning?: unknown }
      if (type !== 'reasoning') return ''
      return typeof reasoning === 'string' ? reasoning : ''
    })
    .join('')
}

/**
 * The thinking a message carries beside its answer.
 *
 * Two shapes reach the browser, and the difference is where the message came
 * from rather than what the model did: while a run streams, the stream SDK
 * lifts the thinking into a `reasoning` content block; the same message read
 * back from the server's state carries it in `additional_kwargs` instead —
 * `reasoning_content`, the field llama-server fills and `ChatDeepSeek` keeps.
 * Either way a message without it simply has no reasoning part, which is what a
 * graph that does not think looks like.
 */
function reasoningOf(message: AgentMessage): string {
  const inBlocks = reasoningInBlocks(message.content)
  if (inBlocks) return inBlocks

  const inKwargs = message.additional_kwargs?.reasoning_content
  return typeof inKwargs === 'string' ? inKwargs : ''
}

function partsOf(message: AgentMessage, results: Map<string, ToolCallResult>): MessagePart[] {
  const parts: MessagePart[] = []

  // The order the graph produced them in: reasoning → tool calls → answer.
  const reasoning = reasoningOf(message)
  if (reasoning) parts.push({ kind: 'reasoning', text: reasoning })

  const calls = ownCalls(message).map((call) => withOutcome(call, results))
  if (calls.length > 0) parts.push({ kind: 'tool_calls', calls })

  const text = textOf(message.content)
  if (text) parts.push({ kind: 'text', text })

  return parts
}

/**
 * Map the server's messages to the feed.
 *
 * Tool results ride inside the call block, so `ToolMessage`s are dropped rather
 * than rendered as rows of their own — as they always have been.
 */
export function toFeed(messages: AgentMessage[]): ChatMessage[] {
  const feed: ChatMessage[] = []
  const results = resultsById(messages)

  messages.forEach((message, i) => {
    const id = message.id ?? `msg-${i}`

    if (message.type === 'human') {
      feed.push({ id, role: 'user', text: textOf(message.content) })
    } else if (message.type === 'system') {
      feed.push({ id, role: 'system', text: textOf(message.content) })
    } else if (message.type === 'ai') {
      const parts = partsOf(message, results)
      // An assistant message with nothing to show would render as an empty
      // bubble — a message that only called a tool carries no text at all.
      if (parts.length > 0) feed.push({ id, role: 'assistant', parts })
    }
  })

  return feed
}
