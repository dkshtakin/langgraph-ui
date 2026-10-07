import { describe, expect, it } from 'vitest'
import { toFeed, type AgentMessage } from './messageParts'

/** A message as the agent server sends it: content is a list of blocks. */
function ai(text: string, over: Partial<AgentMessage> = {}): AgentMessage {
  return {
    id: `ai-${text}`,
    type: 'ai',
    content: [{ type: 'text', text }],
    tool_calls: [],
    invalid_tool_calls: [],
    ...over,
  }
}

/** What a tool answered, as the agent server sends it. */
function tool(content: unknown, over: Partial<AgentMessage> = {}): AgentMessage {
  return {
    id: 'tool-1',
    type: 'tool',
    content,
    tool_call_id: 'c1',
    status: 'success',
    ...over,
  }
}

describe('toFeed — messages', () => {
  it('maps a human message to a user row', () => {
    expect(toFeed([{ id: 'h1', type: 'human', content: 'привет' }])).toEqual([
      { id: 'h1', role: 'user', text: 'привет' },
    ])
  })

  it('maps a system message to a system row', () => {
    expect(toFeed([{ id: 's1', type: 'system', content: 'правила' }])).toEqual([
      { id: 's1', role: 'system', text: 'правила' },
    ])
  })

  it('joins the text of every content block', () => {
    const message = ai('', {
      content: [
        { type: 'text', text: 'раз' },
        { type: 'text', text: 'два' },
      ],
    })
    expect(toFeed([message])).toEqual([
      { id: 'ai-', role: 'assistant', parts: [{ kind: 'text', text: 'раздва' }] },
    ])
  })

  it('drops tool messages — their results live inside the call block', () => {
    const feed = toFeed([{ id: 't1', type: 'tool', content: 'сегодня 7 октября' }])
    expect(feed).toEqual([])
  })

  it('drops an assistant message that has nothing to show', () => {
    expect(toFeed([ai('')])).toEqual([])
  })

  it('falls back to an index id when the server sent none', () => {
    const feed = toFeed([{ type: 'human', content: 'привет' }])
    expect(feed[0].id).toBe('msg-0')
  })
})

describe('toFeed — tool calls', () => {
  const calling = ai('', {
    id: 'ai-1',
    tool_calls: [{ id: 'c1', name: 'today_tool', args: { note: 'сегодня' } }],
  })

  it('renders the call before the text of the same message', () => {
    const message = { ...calling, content: [{ type: 'text', text: 'готово' }] }
    expect(toFeed([message])).toEqual([
      {
        id: 'ai-1',
        role: 'assistant',
        parts: [
          {
            kind: 'tool_calls',
            calls: [{ id: 'c1', name: 'today_tool', args: { note: 'сегодня' } }],
          },
          { kind: 'text', text: 'готово' },
        ],
      },
    ])
  })

  it('marks a call from invalid_tool_calls and keeps its raw arguments', () => {
    const message = ai('', {
      id: 'ai-2',
      invalid_tool_calls: [{ id: 'c2', name: 'today_tool', args: '{"date": ' }],
    })
    expect(toFeed([message])).toEqual([
      {
        id: 'ai-2',
        role: 'assistant',
        parts: [
          {
            kind: 'tool_calls',
            calls: [{ id: 'c2', name: 'today_tool', args: '{"date": ', invalid: true }],
          },
        ],
      },
    ])
  })
})

describe('toFeed — tool results', () => {
  const calling = (calls: AgentMessage['tool_calls']): AgentMessage =>
    ai('', { id: 'ai-1', tool_calls: calls })

  function callsOf(messages: AgentMessage[]) {
    const feed = toFeed(messages)
    const part = feed[0]
    if (part.role !== 'assistant' || part.parts[0].kind !== 'tool_calls') throw new Error('no calls')
    return part.parts[0].calls
  }

  it('shows nothing extra while the call has no answer yet', () => {
    expect(callsOf([calling([{ id: 'c1', name: 'today_tool', args: {} }])])).toEqual([
      { id: 'c1', name: 'today_tool', args: {} },
    ])
  })

  it('carries the returned value once the tool has answered', () => {
    const calls = callsOf([
      calling([{ id: 'c1', name: 'today_tool', args: {} }]),
      tool('7 октября 2026'),
    ])
    expect(calls[0].result).toEqual({ status: 'completed', text: '7 октября 2026' })
  })

  it('pretty-prints a structured return value', () => {
    const calls = callsOf([
      calling([{ id: 'c1', name: 'today_tool', args: {} }]),
      tool({ date: '2026-10-07' }),
    ])
    expect(calls[0].result?.text).toBe('{\n  "date": "2026-10-07"\n}')
  })

  it('carries the failure text of a tool that errored', () => {
    const calls = callsOf([
      calling([{ id: 'c1', name: 'today_tool', args: {} }]),
      tool('инструмент недоступен', { status: 'error' }),
    ])
    expect(calls[0].result).toEqual({ status: 'error', text: 'инструмент недоступен' })
  })

  it('leaves a call alone when no tool message answers it', () => {
    const calls = callsOf([calling([{ id: 'c9', name: 'today_tool', args: {} }]), tool('x')])
    expect(calls[0].result).toBeUndefined()
  })

  it('matches answers to calls by id, not by position', () => {
    const calls = callsOf([
      calling([
        { id: 'c1', name: 'a', args: {} },
        { id: 'c2', name: 'b', args: {} },
      ]),
      tool('второй', { id: 'tool-2', tool_call_id: 'c2' }),
      tool('первый', { id: 'tool-1', tool_call_id: 'c1' }),
    ])
    expect(calls.map((c) => c.result?.text)).toEqual(['первый', 'второй'])
  })
})

describe('toFeed — reasoning', () => {
  const thinking = { additional_kwargs: { reasoning_content: 'думаю' } }

  it('puts the reasoning before the answer of the same message', () => {
    expect(toFeed([ai('готово', { id: 'ai-1', ...thinking })])).toEqual([
      {
        id: 'ai-1',
        role: 'assistant',
        parts: [
          { kind: 'reasoning', text: 'думаю' },
          { kind: 'text', text: 'готово' },
        ],
      },
    ])
  })

  it('puts the reasoning before the tool calls of the same message', () => {
    const message = ai('', {
      id: 'ai-1',
      tool_calls: [{ id: 'c1', name: 'today_tool', args: {} }],
      ...thinking,
    })
    expect(toFeed([message])).toEqual([
      {
        id: 'ai-1',
        role: 'assistant',
        parts: [
          { kind: 'reasoning', text: 'думаю' },
          { kind: 'tool_calls', calls: [{ id: 'c1', name: 'today_tool', args: {} }] },
        ],
      },
    ])
  })

  it('keeps a message that holds nothing but reasoning', () => {
    expect(toFeed([ai('', { id: 'ai-1', ...thinking })])).toEqual([
      { id: 'ai-1', role: 'assistant', parts: [{ kind: 'reasoning', text: 'думаю' }] },
    ])
  })

  it('adds no reasoning part when the field is absent or not a string', () => {
    const textOnly = [{ id: 'ai-1', role: 'assistant', parts: [{ kind: 'text', text: 'готово' }] }]
    expect(toFeed([ai('готово', { id: 'ai-1', additional_kwargs: {} })])).toEqual(textOnly)
    expect(toFeed([ai('готово', { id: 'ai-1', additional_kwargs: { reasoning_content: 42 } })]))
      .toEqual(textOnly)
  })

  it('reads reasoning that arrived as a content block, not as the answer', () => {
    const message = ai('', {
      id: 'ai-1',
      content: [
        { type: 'reasoning', reasoning: 'думаю' },
        { type: 'text', text: 'ответ' },
      ],
    })
    expect(toFeed([message])).toEqual([
      {
        id: 'ai-1',
        role: 'assistant',
        parts: [
          { kind: 'reasoning', text: 'думаю' },
          { kind: 'text', text: 'ответ' },
        ],
      },
    ])
  })
})

describe('toFeed — a real turn from the chat graph', () => {
  // The model's thinking comes back beside the answer, under
  // `additional_kwargs.reasoning_content`, so nothing has to be taken apart.
  it('renders the thinking and the answer of one turn', () => {
    const message = ai('Сегодня **7 октября 2026 года**.', {
      id: 'ai-1',
      additional_kwargs: { reasoning_content: 'Спросили дату — вызову инструмент.' },
      tool_calls: [{ id: 'c1', name: 'today_tool', args: { note: 'сегодня' } }],
    })
    expect(toFeed([message, tool('2026-10-07')])).toEqual([
      {
        id: 'ai-1',
        role: 'assistant',
        parts: [
          { kind: 'reasoning', text: 'Спросили дату — вызову инструмент.' },
          {
            kind: 'tool_calls',
            calls: [
              {
                id: 'c1',
                name: 'today_tool',
                args: { note: 'сегодня' },
                result: { status: 'completed', text: '2026-10-07' },
              },
            ],
          },
          { kind: 'text', text: 'Сегодня **7 октября 2026 года**.' },
        ],
      },
    ])
  })
})
