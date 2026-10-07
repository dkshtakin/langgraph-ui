/**
 * Reading a thread the way the UI needs it.
 *
 * A thread's only name is `metadata.title`, which this app writes when it
 * creates the thread and on rename; its graph id lives in the same metadata.
 * Both are read here so no component has to know how the server nests them.
 */

import type { Thread } from './api/agentServer'

function pad(n: number): string {
  return String(n).padStart(2, '0')
}

/** The graph a thread runs, as the server records it. */
export function graphIdOf(thread: Thread): string {
  const graphId = thread.metadata?.graph_id
  return typeof graphId === 'string' ? graphId : ''
}

/** `<graph id> <date>` — how this app titles a thread it creates. */
export function defaultTitle(graphId: string, createdAt: string | number): string {
  const date = new Date(createdAt)
  return `${graphId} ${pad(date.getDate())}.${pad(date.getMonth() + 1)}.${date.getFullYear()}`
}

/**
 * A thread made by something other than this app has no title; it shows as the
 * graph it runs plus the day it was created rather than as a blank row.
 */
export function threadTitle(thread: Thread): string {
  const title = thread.metadata?.title
  if (typeof title === 'string' && title.trim()) return title
  return defaultTitle(graphIdOf(thread) || 'chat', thread.created_at)
}
