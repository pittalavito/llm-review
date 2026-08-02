/**
 * Typed HTTP client for the llm-review-2 backend.
 * Endpoints are already namespaced (/chat, /agent), so there is no base prefix;
 * in dev they are proxied to the backend on :8081 (see vite.config.ts).
 */
import type { AgentRole, AppConfig, ChatModelName, ChatResponse, CreateGraphReviewRequest, CreateInstructionRequest, CreateOpenReviewPaperRequest, CreatePaperRequest, CreatePaperResponse, CreatePromptRequest, GraphReviewConfigResponse, GraphReviewRecordResponse, GraphReviewSummaryResponse, IndexPaperAccepted, IndexPaperRequest, IndexStatusResponse, PaperListResponse, PaperType, PromptInstruction, PromptInstructionListResponse, PromptInstructionResponse, PromptPreviewRequest, PromptPreviewResponse, PromptVersion, PromptVersionListResponse, PromptVersionResponse, RagStrategy, UpdateInstructionRequest, UpdatePromptRequest } from './types';

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

async function put<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(path, {
    method: 'PUT',
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

/** The paper catalog — DB rows only (unwrapped from PaperListResponse). */
export const listPapers = () =>
  get<PaperListResponse>('/paper/list').then((r) => r.papers);

/** The saved paper (unwrapped from CreatePaperResponse). */
export const createPaper = (request: CreatePaperRequest) =>
  post<CreatePaperResponse>('/paper/create', request).then((r) => r.paper);

/** Create a paper from an OpenReview forum — no file upload: the BE downloads
 * the PDF from the uri inside the notes (unwrapped from CreatePaperResponse). */
export const createOpenreviewPaper = (request: CreateOpenReviewPaperRequest) =>
  post<CreatePaperResponse>('/paper/create-openreview', request).then((r) => r.paper);

export const listRetrievalStrategies = () => get<RagStrategy[]>('/retrieval/strategy-types');

/** 202: the indexing job runs in background — poll getIndexStatus for completion. */
export const indexPaper = (request: IndexPaperRequest) =>
  post<IndexPaperAccepted>('/retrieval/index', request);

/** IndexInfo when the index is built, null otherwise (unwrapped from IndexStatusResponse). */
export const getIndexStatus = (paperId: string, strategy: RagStrategy, strategyVersion = 'v1') => {
  const params = new URLSearchParams({ paper_id: paperId, strategy, strategy_version: strategyVersion });
  return get<IndexStatusResponse>(`/retrieval/index/status?${params}`).then((r) => r.index_info);
};

// ---------------------------------------------------------------------------
// Prompt registry
// ---------------------------------------------------------------------------

/** The whole prompt-version registry (unwrapped). */
export const listPrompts = (includeInactive = false) =>
  get<PromptVersionListResponse>(`/prompts/list?include_inactive=${includeInactive}`).then((r) => r.prompts as PromptVersion[]);

/** The prompt versions registered for one agent role (unwrapped). */
export const listPromptsByRole = (agentRole: string) =>
  get<PromptVersionListResponse>(`/prompts/role/${encodeURIComponent(agentRole)}`).then((r) => r.prompts as PromptVersion[]);

/** The whole persona-instruction registry (unwrapped). */
export const listInstructions = (includeInactive = false) =>
  get<PromptInstructionListResponse>(`/prompts/instructions/list?include_inactive=${includeInactive}`).then((r) => r.instructions as PromptInstruction[]);

/** The composed system prompt (base template + instructions) an agent would
 * receive — the exact string the BE will use (unwrapped). */
export const previewPrompt = (request: PromptPreviewRequest) =>
  post<PromptPreviewResponse>('/prompts/preview', request).then((r) => r.prompt);

/** Register a new immutable prompt version (409 when (role, version) exists). */
export const createPrompt = (request: CreatePromptRequest) =>
  post<PromptVersionResponse>('/prompts/create', request).then((r) => r.prompt);

/** Register a new immutable persona instruction (409 when (type, label) exists). */
export const createInstruction = (request: CreateInstructionRequest) =>
  post<PromptInstructionResponse>('/prompts/instructions/create', request).then((r) => r.instruction);

/** Update a prompt version's mutable metadata (description, is_active) — the
 * template never changes (unwrapped). */
export const updatePrompt = (versionId: number, request: UpdatePromptRequest) =>
  put<PromptVersionResponse>(`/prompts/${versionId}`, request).then((r) => r.prompt);

/** Update an instruction's mutable metadata (description, is_active) — the
 * text never changes (unwrapped). */
export const updateInstruction = (instructionId: number, request: UpdateInstructionRequest) =>
  put<PromptInstructionResponse>(`/prompts/instructions/${instructionId}`, request).then((r) => r.instruction);

// ---------------------------------------------------------------------------
// Review graph
// ---------------------------------------------------------------------------

/** Run history — lightweight summaries, most recent first (unwrapped). */
export const listGraphRuns = () =>
  get<GraphReviewSummaryResponse>('/graph/runs').then((r) => r.summaries);

/** One full run — record rebuilt from the agent traces, agent_records included
 * (unwrapped from GraphReviewRecordResponse). */
export const getGraphRun = (runId: string) =>
  get<GraphReviewRecordResponse>(`/graph/runs/${encodeURIComponent(runId)}`).then((r) => r.record);

/** The configuration currently loaded in the graph service. */
export const getGraphConfig = () => get<GraphReviewConfigResponse>('/graph/config');

/** Build the agents from the config and compile the review graph; echoes the
 * compiled configuration back. */
export const compileGraph = (request: CreateGraphReviewRequest) =>
  post<GraphReviewConfigResponse>('/graph/compile', request);

/** Run the compiled graph on the paper; persists and returns the full record
 * (unwrapped from GraphReviewRecordResponse). */
export const invokeGraph = (request: CreateGraphReviewRequest) =>
  post<GraphReviewRecordResponse>('/graph/invoke', request).then((r) => r.record);
