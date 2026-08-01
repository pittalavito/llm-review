/**
 * Typed HTTP client for the llm-review-2 backend.
 * Endpoints are already namespaced (/chat, /agent), so there is no base prefix;
 * in dev they are proxied to the backend on :8081 (see vite.config.ts).
 */
import type { AgentRole, AppConfig, ChatModelName, ChatResponse, CreateGraphReviewRequest, CreatePaperRequest, GraphReviewConfigResponse, GraphReviewRecord, GraphReviewSummary, IndexInfo, IndexPaperAccepted, IndexPaperRequest, Paper, PaperType, RagStrategy } from './types';

export class ApiError extends Error {}

async function readJsonOrText(response: Response): Promise<unknown> {
  const contentType = response.headers.get('content-type') || '';
  return contentType.includes('application/json') ? response.json() : response.text();
}

async function throwForResponse(response: Response): Promise<void> {
  if (response.ok) return;
  const payload = await readJsonOrText(response);
  const detail =
    typeof payload === 'string'
      ? payload
      : (payload as { detail?: unknown })?.detail;
  if (typeof detail === 'string') throw new ApiError(detail);
  if (detail && typeof detail === 'object') throw new ApiError(JSON.stringify(detail));
  throw new ApiError(`HTTP ${response.status} ${response.statusText}`);
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(path);
  await throwForResponse(res);
  return res.json() as Promise<T>;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  await throwForResponse(res);
  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Catalogs
// ---------------------------------------------------------------------------

export const listModels = () => get<ChatModelName[]>('/chat/models');
export const listRoles = () => get<AgentRole[]>('/agent/roles');
export const getAdminConfig = () => get<AppConfig>('/admin/config');

// ---------------------------------------------------------------------------
// Ping chat — single-turn LLM tester
// ---------------------------------------------------------------------------

export const pingChat = (message: string, model: string, temperature = 0.7) =>
  post<ChatResponse>('/chat/ping', { message, model, temperature });

// ---------------------------------------------------------------------------
// Papers
// ---------------------------------------------------------------------------

export const listPaperTypes = () => get<PaperType[]>('/paper/types');

/** The paper catalog — DB rows only. */
export const listPapers = () => get<Paper[]>('/paper/list');

export const createPaper = (request: CreatePaperRequest) =>
  post<Paper>('/paper/create', request);

export const listRetrievalStrategies = () => get<RagStrategy[]>('/retrieval/strategy-types');

/** 202: the indexing job runs in background — poll getIndexStatus for completion. */
export const indexPaper = (request: IndexPaperRequest) =>
  post<IndexPaperAccepted>('/retrieval/index', request);

/** IndexInfo when the index is built, null otherwise. */
export const getIndexStatus = (paperId: string, strategy: RagStrategy, strategyVersion = 'v1') => {
  const params = new URLSearchParams({ paper_id: paperId, strategy, strategy_version: strategyVersion });
  return get<IndexInfo | null>(`/retrieval/index/status?${params}`);
};

// ---------------------------------------------------------------------------
// Review graph
// ---------------------------------------------------------------------------

/** Run history — lightweight summaries, most recent first. */
export const listGraphRuns = () => get<GraphReviewSummary[]>('/graph/runs');

/** The configuration currently loaded in the graph service. */
export const getGraphConfig = () => get<GraphReviewConfigResponse>('/graph/config');

/** Build the agents from the config and compile the review graph; echoes the
 * compiled configuration back. */
export const compileGraph = (request: CreateGraphReviewRequest) =>
  post<GraphReviewConfigResponse>('/graph/compile', request);

/** Run the compiled graph on the paper; persists and returns the full record. */
export const invokeGraph = (request: CreateGraphReviewRequest) =>
  post<GraphReviewRecord>('/graph/invoke', request);
