/**
 * Building the ordered parts of an assistant message.
 *
 * Two sources produce the same shape: a live SSE turn, accumulated chunk by
 * chunk, and the stored history, whose flat fields are mapped in one go. Both
 * go through here so the live feed and the reloaded one come out alike.
 */

import type { SerializedMessage } from './api/client'
import type { AssistantMessage, MessagePart, ToolCallEvent } from './types'

/** A text part holding nothing but whitespace renders as nothing. */
function isBlankText(part: MessagePart): boolean {
  return part.kind === 'text' && !part.text.trim()
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

  // A tool call ends the segment, and a whitespace-only text part — the "\n\n"
  // the model emits before calling a tool — goes with it. The history mapping
  // drops that part too, so both sources end up with the same sequence.
  const parts = part.kind === 'tool_calls' && isBlankText(lastPart)
    ? last.parts.slice(0, -1)
    : last.parts

  return [...messages.slice(0, -1), { ...last, parts: mergePart(parts, part) }]
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

/** Build the parts of an assistant message from the flat fields history returns. */
export function historyParts(message: SerializedMessage): MessagePart[] {
  const parts: MessagePart[] = []
  if (message.reasoning) parts.push({ kind: 'reasoning', text: message.reasoning })
  if (message.toolCalls?.length) parts.push({ kind: 'tool_calls', calls: message.toolCalls })
  if (message.text?.trim()) parts.push({ kind: 'text', text: message.text })
  return parts
}
