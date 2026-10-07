/**
 * The one place that knows the agent server exists.
 *
 * Everything the app needs from the server goes through here: the URL the
 * streaming hook is pointed at, the thread list the sidebar shows, and the
 * graph list the dropdown offers. The calls are plain `Client` calls from
 * `@langchain/langgraph-sdk` — this module exists to keep the SDK's shapes out
 * of the components.
 *
 * Every call logs what it asked for and what came back, so a screen that
 * stayed empty can be told apart from a request that never landed.
 */

import { Client } from '@langchain/langgraph-sdk'
import { describe, log, logError } from '../log'

/** Path the dev server (and, later, production) proxies to the agent server. */
const API_PATH = '/langgraph'

/**
 * The SDK builds request URLs with `new URL(...)`, which rejects a relative
 * base — so the path is resolved against the page's own origin. The browser
 * still sees a same-origin request, so CORS never comes up.
 */
export const API_URL = `${window.location.origin}${API_PATH}`

export const client = new Client({ apiUrl: API_URL })

/** Server-side state of a thread. */
export type ThreadStatus = 'idle' | 'busy' | 'interrupted' | 'error'

export interface Thread {
  thread_id: string
  created_at: string
  updated_at: string
  status: ThreadStatus
  metadata: Record<string, unknown>
}

/**
 * The sidebar has no pagination, so it asks for everything the server will
 * give in one go; 1000 is the largest limit the API accepts.
 */
const LIMIT = 1000

export async function listThreads(): Promise<Thread[]> {
  log(`threads: asking for the newest ${LIMIT}`)
  try {
    const threads = (await client.threads.search({
      limit: LIMIT,
      sortBy: 'created_at',
      sortOrder: 'desc',
    })) as Thread[]
    log(`threads: got ${threads.length}`)
    return threads
  } catch (err) {
    logError('threads: request failed —', describe(err))
    throw err
  }
}

/**
 * Graph ids, deduplicated: `graph_id` is not unique — every version of a graph
 * or a second assistant over it adds another row. The id is also the display
 * name, since `langgraph.json` keys are what the user reads.
 */
export async function listGraphs(): Promise<string[]> {
  log('graphs: asking for assistants')
  try {
    const assistants = await client.assistants.search({ limit: LIMIT })
    const ids = [
      ...new Set(assistants.map((a) => a.graph_id).filter((id): id is string => Boolean(id))),
    ]
    log('graphs: got', ids.length ? ids : '(none)')
    return ids
  } catch (err) {
    logError('graphs: request failed —', describe(err))
    throw err
  }
}

export async function createThread(graphId: string, title: string): Promise<Thread> {
  log(`creating a thread on "${graphId}" titled "${title}"`)
  try {
    // `graphId` is not a field of the thread: the SDK folds it into the
    // metadata as `graph_id`, which is where the sidebar reads it back from.
    const thread = (await client.threads.create({
      graphId,
      metadata: { title },
    })) as Thread
    log(`created thread ${thread.thread_id} (graph "${graphId}")`)
    return thread
  } catch (err) {
    logError('creating a thread failed —', describe(err))
    throw err
  }
}

/**
 * Metadata is merged, not replaced, so the server's own `graph_id` and
 * `assistant_id` keys survive a rename.
 */
export async function renameThread(threadId: string, title: string): Promise<void> {
  log(`renaming ${threadId} to "${title}"`)
  try {
    await client.threads.update(threadId, { metadata: { title } })
  } catch (err) {
    logError(`renaming ${threadId} failed —`, describe(err))
    throw err
  }
}

export async function deleteThread(threadId: string): Promise<void> {
  log(`deleting ${threadId}`)
  try {
    await client.threads.delete(threadId)
  } catch (err) {
    logError(`deleting ${threadId} failed —`, describe(err))
    throw err
  }
}
