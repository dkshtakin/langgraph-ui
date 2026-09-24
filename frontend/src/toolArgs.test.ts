import { describe, expect, it } from 'vitest'
import { stringifyArgs } from './toolArgs'

describe('stringifyArgs', () => {
  it('pretty-prints an object, and renders nothing when it is empty', () => {
    expect(stringifyArgs({ date: '2026-09-23', note: 'сегодня' })).toBe(
      '{\n  "date": "2026-09-23",\n  "note": "сегодня"\n}',
    )
    expect(stringifyArgs({})).toBe('')
  })

  it('passes the raw string of an unparsed call through as-is', () => {
    expect(stringifyArgs('{"date": ')).toBe('{"date": ')
  })

  it('renders nothing for null and for missing args', () => {
    expect(stringifyArgs(null)).toBe('')
    expect(stringifyArgs(undefined)).toBe('')
  })
})
