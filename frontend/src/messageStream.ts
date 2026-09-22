/**
 * Accumulation rules for a live assistant turn.
 *
 * The SSE stream carries no message boundary, so the frontend has to infer the
 * grouping the backend already produces: a tool call closes the current
 * assistant message, and the next non-tool part opens a new one.
 */

import type { AssistantMessage, MessagePart, ToolCallEvent } from './types'

/** A tool call closes a message: the next non-tool part opens a new one. */
function appendPart(
  messages: AssistantMessage[],
  part: MessagePart,
  newMessageId: string,
): AssistantMessage[] {
  const last = messages[messages.length - 1]
  const lastPart = last?.parts[last.parts.length - 1]

  if (!last || (lastPart.kind === 'tool_calls' && part.kind !== 'tool_calls')) {
    return [...messages, { id: newMessageId, role: 'assistant', parts: [part] }]
  }

  return [...messages.slice(0, -1), { ...last, parts: mergePart(last.parts, part) }]
}

/** Merge a part into the last part of `parts` when the kind matches, else append. */
function mergePart(parts: MessagePart[], part: MessagePart): MessagePart[] {
  const last = parts[parts.length - 1]

  if (last?.kind === 'text' && part.kind === 'text') {
    return [...parts.slice(0, -1), { kind: 'text', text: last.text + part.text }]
  }
  if (last?.kind === 'reasoning' && part.kind === 'reasoning') {
    return [...parts.slice(0, -1), { kind: 'reasoning', text: last.text + part.text }]
  }
  if (last?.kind === 'tool_calls' && part.kind === 'tool_calls') {
    return [...parts.slice(0, -1), { kind: 'tool_calls', calls: [...last.calls, ...part.calls] }]
  }

  return [...parts, part]
}

/** Append a reasoning or answer chunk, extending the open message. */
export function appendChunk(
  messages: AssistantMessage[],
  kind: 'reasoning' | 'text',
  text: string,
  newMessageId: string,
): AssistantMessage[] {
  return appendPart(messages, { kind, text }, newMessageId)
}

/** Append a tool call, extending the open message. */
export function appendToolCall(
  messages: AssistantMessage[],
  call: ToolCallEvent,
  newMessageId: string,
): AssistantMessage[] {
  return appendPart(messages, { kind: 'tool_calls', calls: [call] }, newMessageId)
}

/**
 * Build the parts of an assistant message from the flat fields the history
 * endpoint returns — the order the history has always rendered in.
 */
export function historyParts(message: {
  text: string | null
  reasoning: string | null
  toolCalls?: ToolCallEvent[]
}): MessagePart[] {
  const parts: MessagePart[] = []
  if (message.reasoning) parts.push({ kind: 'reasoning', text: message.reasoning })
  if (message.toolCalls?.length) parts.push({ kind: 'tool_calls', calls: message.toolCalls })
  if (message.text) parts.push({ kind: 'text', text: message.text })
  return parts
}
