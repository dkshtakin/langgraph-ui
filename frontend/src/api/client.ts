import type { ToolCallArgs } from '../types'

export interface Session {
  session_id: string
  thread_id: string
  graph_id: string
  graph_name: string
  title: string
  status?: string
  created_at: number
  updated_at: number
}

export async function getSessions(): Promise<Session[]> {
  const res = await fetch('/api/sessions')
  if (!res.ok) {
    throw new Error(`Failed to list sessions: ${res.status} ${res.statusText}`)
  }
  const body = (await res.json()) as { sessions: Session[] }
  return body.sessions
}

export async function createSession(graphId = 'book_planner'): Promise<Session> {
  const res = await fetch('/api/sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ graph_id: graphId }),
  })
  if (!res.ok) {
    throw new Error(`Failed to create session: ${res.status} ${res.statusText}`)
  }
  return res.json() as Promise<Session>
}

export async function renameSession(sessionId: string, title: string): Promise<Session> {
  const res = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  })
  if (!res.ok) {
    throw new Error(`Failed to rename session: ${res.status} ${res.statusText}`)
  }
  return res.json() as Promise<Session>
}

export interface GraphInfo {
  id: string
  name: string
}

export async function getGraphs(): Promise<GraphInfo[]> {
  const res = await fetch('/api/graphs')
  if (!res.ok) {
    throw new Error(`Failed to list graphs: ${res.status} ${res.statusText}`)
  }
  const body = (await res.json()) as { graphs: Record<string, { name: string }> }
  return Object.entries(body.graphs).map(([id, g]) => ({ id, name: g.name }))
}

export async function deleteSession(sessionId: string): Promise<void> {
  const res = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}`, {
    method: 'DELETE',
  })
  if (!res.ok && res.status !== 200) {
    throw new Error(`Failed to delete session: ${res.status}`)
  }
}

export interface SerializedMessage {
  role: string
  text: string | null
  reasoning: string | null
  toolCalls?: Array<{ name: string; args: ToolCallArgs }>
}

export async function getMessages(sessionId: string): Promise<SerializedMessage[]> {
  const res = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/messages`)
  if (!res.ok) {
    throw new Error(`Failed to load messages: ${res.status} ${res.statusText}`)
  }
  const body = (await res.json()) as { messages: SerializedMessage[] }
  return body.messages
}
