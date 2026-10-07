import { describe, expect, it } from 'vitest'
import { dotClass, streamStateOf, type StreamSignals } from './streamState'
import type { StreamState } from './types'

const signals = (over: Partial<StreamSignals> = {}): StreamSignals => ({
  isLoading: false,
  isThreadLoading: false,
  hasMessages: false,
  interrupts: 0,
  ...over,
})

describe('streamStateOf', () => {
  it('reports streaming while a run is active over existing messages', () => {
    expect(streamStateOf(signals({ isLoading: true, hasMessages: true }))).toBe('streaming')
  })

  it('reports initializing while the opening run has produced nothing yet', () => {
    expect(streamStateOf(signals({ isLoading: true }))).toBe('initializing')
  })

  it('reports interrupted when the thread is parked on an interrupt', () => {
    expect(streamStateOf(signals({ interrupts: 1, hasMessages: true }))).toBe('interrupted')
  })

  it('reports done when a finished run left messages behind', () => {
    expect(streamStateOf(signals({ hasMessages: true }))).toBe('done')
  })

  it('reports idle for a thread with no messages and no interrupts', () => {
    expect(streamStateOf(signals())).toBe('idle')
  })

  it('keeps the input shut while history is still loading', () => {
    expect(streamStateOf(signals({ isThreadLoading: true }))).toBe('initializing')
    expect(streamStateOf(signals({ isThreadLoading: true, hasMessages: true }))).toBe('streaming')
  })

  it('does not call a thread interrupted while a run is still going', () => {
    expect(streamStateOf(signals({ isLoading: true, interrupts: 1, hasMessages: true }))).toBe(
      'streaming',
    )
  })
})

describe('dotClass', () => {
  it('gives every state its own dot', () => {
    const states: StreamState[] = ['idle', 'initializing', 'streaming', 'interrupted', 'done']
    expect(states.map((s) => dotClass(s, false))).toEqual([
      'dot-idle',
      'dot-streaming',
      'dot-streaming',
      'dot-paused',
      'dot-completed',
    ])
  })

  it('reports a failed thread whatever else it is doing', () => {
    expect(dotClass('done', true)).toBe('dot-error')
    expect(dotClass('interrupted', true)).toBe('dot-error')
  })
})
