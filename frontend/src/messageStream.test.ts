import { describe, expect, it } from 'vitest'
import { appendChunk, appendToolCall } from './messageStream'
import type { AssistantMessage, MessagePart, ToolCallEvent } from './types'

function toolCall(name: string): ToolCallEvent {
  return { name, args: {}, invalid: false }
}

/** Feed an event sequence through the accumulators the way the live stream does. */
function feed(events: Array<['reasoning' | 'text', string] | ['tool', string]>): AssistantMessage[] {
  let messages: AssistantMessage[] = []
  let id = 0
  for (const [kind, value] of events) {
    id += 1
    messages =
      kind === 'tool'
        ? appendToolCall(messages, toolCall(value), `m${id}`)
        : appendChunk(messages, kind, value, `m${id}`)
  }
  return messages
}

function partsOf(messages: AssistantMessage[]): MessagePart[][] {
  return messages.map((m) => m.parts)
}

describe('merging parts', () => {
  it('merges consecutive chunks of the same kind into one part', () => {
    const messages = feed([['reasoning', 'думаю'], ['reasoning', ' ещё']])
    expect(partsOf(messages)).toEqual([[{ kind: 'reasoning', text: 'думаю ещё' }]])
  })

  it('opens a new part when the kind changes', () => {
    const messages = feed([['reasoning', 'думаю'], ['text', 'отвечаю']])
    expect(partsOf(messages)).toEqual([
      [{ kind: 'reasoning', text: 'думаю' }, { kind: 'text', text: 'отвечаю' }],
    ])
  })

  it('starts a message on the first chunk', () => {
    const messages = feed([['text', 'привет']])
    expect(partsOf(messages)).toEqual([[{ kind: 'text', text: 'привет' }]])
  })

  it('does not mutate the messages it is given', () => {
    const before = feed([['reasoning', 'думаю']])
    const snapshot = structuredClone(before)

    appendChunk(before, 'reasoning', ' ещё', 'm9')
    appendToolCall(before, toolCall('today_tool'), 'm9')

    expect(before).toEqual(snapshot)
  })
})

describe('tool call boundaries', () => {
  it('keeps a tool call in the message that precedes it', () => {
    const messages = feed([['reasoning', 'нужно вызвать today_tool'], ['tool', 'today_tool']])
    expect(partsOf(messages)).toEqual([
      [
        { kind: 'reasoning', text: 'нужно вызвать today_tool' },
        { kind: 'tool_calls', calls: [toolCall('today_tool')] },
      ],
    ])
  })

  it('opens a message for a tool call that comes first', () => {
    const messages = feed([['tool', 'today_tool']])
    expect(partsOf(messages)).toEqual([[{ kind: 'tool_calls', calls: [toolCall('today_tool')] }]])
  })

  it('opens a new message for text that follows a tool call', () => {
    const messages = feed([['reasoning', 'думаю'], ['tool', 'today_tool'], ['text', 'готово']])
    expect(partsOf(messages)).toEqual([
      [
        { kind: 'reasoning', text: 'думаю' },
        { kind: 'tool_calls', calls: [toolCall('today_tool')] },
      ],
      [{ kind: 'text', text: 'готово' }],
    ])
  })

  it('opens a new message for reasoning that follows a tool call', () => {
    const messages = feed([['reasoning', 'думаю'], ['tool', 'today_tool'], ['reasoning', 'ещё думаю']])
    expect(partsOf(messages)).toEqual([
      [
        { kind: 'reasoning', text: 'думаю' },
        { kind: 'tool_calls', calls: [toolCall('today_tool')] },
      ],
      [{ kind: 'reasoning', text: 'ещё думаю' }],
    ])
  })

  it('keeps parallel tool calls in one message', () => {
    const messages = feed([['reasoning', 'два вызова'], ['tool', 'a'], ['tool', 'b'], ['text', 'готово']])
    expect(partsOf(messages)).toEqual([
      [
        { kind: 'reasoning', text: 'два вызова' },
        { kind: 'tool_calls', calls: [toolCall('a'), toolCall('b')] },
      ],
      [{ kind: 'text', text: 'готово' }],
    ])
  })

  it('gives every message its own id', () => {
    const messages = feed([['tool', 'a'], ['text', 'b']])
    expect(messages.map((m) => m.id)).toEqual(['m1', 'm2'])
  })
})

describe('a real turn from the checkpoint', () => {
  it('splits reasoning → tool → reasoning → text into two messages', () => {
    const messages = feed([
      ['reasoning', '\nПользователь спрашивает, какой сегодня день. '],
      ['reasoning', 'Мне нужно вызвать инструмент today_tool.'],
      ['tool', 'today_tool'],
      ['reasoning', '\nСегодня 18 сентября 2026 года. Нужно ответить пользователю.'],
      ['text', '\n\nСегодня **18 сентября 2026 года**.'],
    ])

    expect(partsOf(messages)).toEqual([
      [
        {
          kind: 'reasoning',
          text: '\nПользователь спрашивает, какой сегодня день. Мне нужно вызвать инструмент today_tool.',
        },
        { kind: 'tool_calls', calls: [toolCall('today_tool')] },
      ],
      [
        { kind: 'reasoning', text: '\nСегодня 18 сентября 2026 года. Нужно ответить пользователю.' },
        { kind: 'text', text: '\n\nСегодня **18 сентября 2026 года**.' },
      ],
    ])
  })
})
