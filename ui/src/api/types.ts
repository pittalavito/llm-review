/**
 * API payload types, hand-derived from the backend Pydantic models
 * (src/domain/models/*.py and src/controller/models.py).
 */

// domain/models/chat.py :: ChatModelName (StrEnum) — serialized as its string value.
export type ChatModelName = string;

// domain/models/agent.py :: AgentRole (StrEnum).
export type AgentRole =
  | 'chat' | 'reviewer' | 'meta_reviewer' | 'area_chair' | 'author_agent';

// controller/models.py :: ChatRequest
export interface ChatRequest {
  model: string;
  temperature: number;
  message: string;
}

// controller/models.py :: ChatResponse — the full ping payload, treated as JSON by the FE.
export interface ChatResponse {
  response: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  total_tokens: number | null;
  parsing_error: string | null;
}

// domain/models/paper.py :: PaperType (StrEnum).
export type PaperType = 'OPEN_REVIEW' | 'OTHER';

// domain/models/paper.py :: Paper.
export interface Paper {
  id?: number | null;
  paper_id: string;
  paper_name: string;
  paper_type: PaperType;
  description?: string | null;
  open_review_id?: string | null;
  conference?: string | null;
  openreview_api_version?: string | null;
  human_decision?: string | null;
  num_graph_review?: number;
}

// models/controller/paper.py :: CreatePaperRequest — file_bytes is base64 in the JSON body.
export interface CreatePaperRequest {
  paper: Paper;
  file_bytes: string;
}

// models/controller/paper.py :: CreatePaperResponse / PaperListResponse.
export interface CreatePaperResponse {
  paper: Paper;
}

export interface PaperListResponse {
  papers: Paper[];
}

// GET /admin/config — the whole backend Config (secrets already masked by the BE).
// Known keys are typed loosely: the shape follows src/config.py and can grow.
export type AppConfig = Record<string, string | number | null>;

// domain/models/retrieval.py :: RagStrategy (StrEnum).
export type RagStrategy = 'full_context' | 'bm25' | 'embedding';

// controller/models.py :: IndexPaperRequest.
export interface IndexPaperRequest {
  paper_id: string;
  strategy: RagStrategy;
  strategy_version?: string;
  force?: boolean;
}

// domain/models/retrieval.py :: IndexInfo — lightweight RAG index metadata.
export interface IndexInfo {
  doc_id: string;
  paper_id: string;
  section_count: number;
}

// models/controller/retrieval.py :: IndexPaperAccepted — 202: the indexing runs in background.
export interface IndexPaperAccepted {
  status: string;
  paper_id: string;
  strategy: RagStrategy;
  strategy_version: string;
}

// models/controller/retrieval.py :: IndexStatusResponse — index_info is null until built.
export interface IndexStatusResponse {
  index_info: IndexInfo | null;
}

// domain/models/agent.py :: ContextMode (StrEnum).
export type ContextMode = 'none' | 'full_context' | 'bm25' | 'embedding';

// domain/models/agent.py :: AgentRequestContext.
export interface AgentRequestContext {
  context_mode: ContextMode;
  retrieval_context_query?: string | null;
}

// The system prompt is structured JSON (free-form object), not plain text.
export type SystemPrompt = Record<string, unknown>;

// domain/models/graph.py :: AgentConfig — LLM settings for one agent role.
// system_prompt is treated as JSON on the FE (edited/validated as an object).
// input_message is FE-only for now: the BE model has no such field yet.
export interface AgentConfig {
  model: string;
  temperature: number;
  system_prompt?: SystemPrompt | null;
  input_message?: string | null;
  request_context: AgentRequestContext;
}

// FE evolution of domain/models/graph.py :: GraphConfig — shared graph-level
// settings are only paper_id, num_reviewers and max_rounds; every reviewer has
// its own AgentConfig (the BE still shares one — alignment pending).
export interface GraphConfig {
  paper_id: string | null;
  num_reviewers: number;
  max_rounds: number;
  reviewers: AgentConfig[];
  meta_reviewer: AgentConfig;
  area_chair: AgentConfig;
  author: AgentConfig;
}

// models/domain/run_record.py :: GraphReviewSummary — lightweight run-history
// row, analytics facts included.
export interface GraphReviewSummary {
  run_id: string;
  timestamp: string;
  paper_id: string;
  description?: string | null;
  decision: string | null;
  total_rounds: number;
  max_rounds?: number | null;
  meta_overall_score?: number | null;
}

// ---------------------------------------------------------------------------
// Backend contract for compile/invoke — mirrors domain/models/graph.py, which
// still shares ONE reviewer config and wants system_prompt as a string. The
// richer FE GraphConfig is mapped onto this shape when launching a run.
// ---------------------------------------------------------------------------

// domain/models/graph.py :: AgentConfig (BE side).
export interface BackendAgentConfig {
  model: string;
  temperature: number;
  system_prompt: string;
  request_context: AgentRequestContext;
}

// domain/models/graph.py :: GraphReviewConfig.
export interface GraphReviewConfig {
  reviewer: BackendAgentConfig;
  meta_reviewer: BackendAgentConfig;
  area_chair: BackendAgentConfig;
  author: BackendAgentConfig;
  num_reviewers: number;
  max_rounds: number;
}

// models/domain/graph.py :: CreateGraphReviewRequest.
export interface CreateGraphReviewRequest {
  paper_id: string;
  graph_config: GraphReviewConfig;
  description?: string;
}

// models/controller/graph.py :: GraphReviewConfigResponse — returned by both
// GET /graph/config (current config) and POST /graph/compile (echo of the
// compiled config).
export interface GraphReviewConfigResponse {
  graph_config: GraphReviewConfig;
}

// models/controller/graph.py :: GraphReviewRecordResponse / GraphReviewSummaryResponse.
export interface GraphReviewRecordResponse {
  record: GraphReviewRecord;
}

export interface GraphReviewSummaryResponse {
  summaries: GraphReviewSummary[];
}

// models/domain/run_record.py :: GraphReviewRecord — the fields the FE shows.
export interface GraphReviewRecord {
  run_id: string;
  timestamp: string;
  paper_id: string;
  description?: string | null;
  decision: string | null;
  total_rounds: number;
  reviews_response?: Record<string, unknown>[] | null;
  meta_review_response?: Record<string, unknown> | null;
  area_chair_response?: Record<string, unknown> | null;
  author_response?: Record<string, unknown> | null;
}
