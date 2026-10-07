import { describe, expect, it } from 'vitest'
import { defaultTitle, graphIdOf, threadTitle } from './thread'
import type { Thread } from './api/agentServer'

function thread(over: Partial<Thread> = {}): Thread {
  return {
    thread_id: 't1',
    created_at: '2026-10-07T13:12:34.788411+00:00',
    updated_at: '2026-10-07T13:12:34.788411+00:00',
    status: 'idle',
    metadata: {},
    ...over,
  }
}

describe('graphIdOf', () => {
  it('reads the graph the server filed the thread under', () => {
    expect(graphIdOf(thread({ metadata: { graph_id: 'chat' } }))).toBe('chat')
  })

  it('is empty when the metadata carries no graph', () => {
    expect(graphIdOf(thread())).toBe('')
  })
})

describe('defaultTitle', () => {
  it('prints the graph id and the creation date', () => {
    expect(defaultTitle('chat', new Date(2026, 9, 7).getTime())).toBe('chat 07.10.2026')
  })

  it('pads a single-digit day and month', () => {
    expect(defaultTitle('agent', new Date(2026, 0, 3).getTime())).toBe('agent 03.01.2026')
  })
})

describe('threadTitle', () => {
  it('prefers the title this app wrote', () => {
    expect(threadTitle(thread({ metadata: { title: 'Мой тред', graph_id: 'chat' } }))).toBe('Мой тред')
  })

  it('falls back to graph and date for a thread made elsewhere', () => {
    expect(threadTitle(thread({ metadata: { graph_id: 'chat' } }))).toBe('chat 07.10.2026')
  })

  it('treats a blank title as no title', () => {
    expect(threadTitle(thread({ metadata: { title: '   ', graph_id: 'chat' } }))).toBe('chat 07.10.2026')
  })

  it('falls back to the chat graph when even the metadata is missing', () => {
    expect(threadTitle(thread())).toBe('chat 07.10.2026')
  })
})
