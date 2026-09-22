import { describe, expect, it } from 'vitest'
import { appendChunk, appendToolCall, historyParts } from './messageParts'
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

describe('whitespace-only text', () => {
  it('drops a blank text part when a tool call closes the segment', () => {
    const messages = feed([['reasoning', 'думаю'], ['text', '\n\n'], ['tool', 'today_tool']])
    expect(partsOf(messages)).toEqual([
      [
        { kind: 'reasoning', text: 'думаю' },
        { kind: 'tool_calls', calls: [toolCall('today_tool')] },
      ],
    ])
  })

  it('keeps a text part that carries anything but whitespace', () => {
    const messages = feed([['reasoning', 'думаю'], ['text', '\n\nготово'], ['tool', 'today_tool']])
    expect(partsOf(messages)).toEqual([
      [
        { kind: 'reasoning', text: 'думаю' },
        { kind: 'text', text: '\n\nготово' },
        { kind: 'tool_calls', calls: [toolCall('today_tool')] },
      ],
    ])
  })
})

describe('historyParts', () => {
  it('skips a whitespace-only text', () => {
    expect(historyParts({ role: 'assistant', text: '\n\n', reasoning: 'думаю', toolCalls: [toolCall('today_tool')] }))
      .toEqual([
        { kind: 'reasoning', text: 'думаю' },
        { kind: 'tool_calls', calls: [toolCall('today_tool')] },
      ])
  })

  it('keeps the order reasoning → tool calls → text', () => {
    expect(historyParts({ role: 'assistant', text: 'ответ', reasoning: 'думаю', toolCalls: [toolCall('a')] }))
      .toEqual([
        { kind: 'reasoning', text: 'думаю' },
        { kind: 'tool_calls', calls: [toolCall('a')] },
        { kind: 'text', text: 'ответ' },
      ])
  })
})

describe('a real turn from the checkpoint', () => {
  // The stream emits a message's text block before its tool call, so the
  // whitespace tail arrives ahead of the tool; history carries it after.
  const streamed = feed([
    ['reasoning', '\nПользователь спрашивает, какой сегодня день. '],
    ['reasoning', 'Мне нужно вызвать инструмент today_tool.'],
    ['text', '\n\n'],
    ['tool', 'today_tool'],
    ['reasoning', '\nСегодня 18 сентября 2026 года. Нужно ответить пользователю.'],
    ['text', '\n\nСегодня **18 сентября 2026 года**.'],
  ])

  const history = [
    {
      role: 'assistant',
      text: '\n\n',
      reasoning: '\nПользователь спрашивает, какой сегодня день. Мне нужно вызвать инструмент today_tool.',
      toolCalls: [toolCall('today_tool')],
    },
    {
      role: 'assistant',
      text: '\n\nСегодня **18 сентября 2026 года**.',
      reasoning: '\nСегодня 18 сентября 2026 года. Нужно ответить пользователю.',
      toolCalls: [],
    },
  ].map((m, i) => ({ id: `h${i}`, role: 'assistant' as const, parts: historyParts(m) }))

  it('splits reasoning → tool → reasoning → text into two messages', () => {
    expect(partsOf(streamed)).toEqual([
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

  it('gives the same parts as the history mapping', () => {
    expect(partsOf(streamed)).toEqual(partsOf(history))
  })
})
