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

// models/controller/paper.py :: OpenReviewItem — one parsed OpenReview note
// (human reviewer / meta review / area chair decision) from the open_review table.
export interface OpenReviewItem {
  note_id: string;
  reviewer_type: 'reviewer' | 'meta_reviewer' | 'area_chair';
  reviewer_id?: string | null;
  reviewer_index?: number | null;
  rating?: number | null;
  confidence?: number | null;
  overall_score?: number | null;
  decision?: string | null;
  recommendation?: string | null;
  significance_and_novelty?: string | null;
  review_text?: string | null;
  summary?: string | null;
  justification?: string | null;
}

// models/controller/paper.py :: OpenReviewDataResponse.
export interface OpenReviewDataResponse {
  paper_id: string;
  reviews: OpenReviewItem[];
}

// models/domain/paper.py :: Author — position is the 1-based slot in the
// paper's author list.
export interface Author {
  id?: number | null;
  full_name: string;
  email?: string | null;
  affiliation?: string | null;
  openreview_profile_id?: string | null;
  position?: number | null;
}

// models/controller/paper.py :: CreatePaperRequest — file_bytes is base64 in
// the JSON body; paper.paper_name is the user-typed name, file_name carries
// the original file name (the BE takes the format and generates the uid
// paper_id); authors (optional) are linked to the paper in list order.
export interface CreatePaperRequest {
  paper: Paper;
  file_name: string;
  file_bytes: string;
  authors?: Author[];
}

// models/controller/paper.py :: CreateOpenReviewPaperRequest — the FE parses
// the pasted notes response and ships the extracted fields ready-to-use
// (paper_name, ordered authors, human_decision) plus the PDF base64 in
// file_bytes (the browser downloads it — openreview.net blocks server fetches);
// notes stays verbatim for the BE cache.
export interface CreateOpenReviewPaperRequest {
  conference: string;
  forum_id: string;
  paper_name: string;
  file_bytes: string;
  authors?: Author[];
  human_decision?: string | null;
  description?: string | null;
  notes: Record<string, unknown>[];
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

// models/domain/agent.py :: AgentSystemPromptRequest — the prompt is composed
// on the BE from a registered base version plus persona instruction labels.
export interface AgentSystemPromptRequest {
  base_prompt_version: string | null;
  instruction_labels: string[];
}

// models/domain/graph.py :: AgentConfig — LLM settings for one agent role.
// input_message is FE-only for now: the BE model has no such field yet.
export interface AgentConfig {
  model: string;
  temperature: number;
  system_prompt_request?: AgentSystemPromptRequest | null;
  input_message?: string | null;
  request_context: AgentRequestContext;
}

// FE evolution of domain/models/graph.py :: GraphConfig — shared graph-level
// settings are only paper_id, num_reviewers and max_rounds; every reviewer has
// its own AgentConfig, mirrored 1:1 by the BE `reviewers` list.
export interface GraphConfig {
  paper_id: string | null;
  num_reviewers: number;
  max_rounds: number;
  reviewers: AgentConfig[];
  meta_reviewer: AgentConfig;
  area_chair: AgentConfig;
  author: AgentConfig;
}

// models/domain/prompt.py :: PromptVersion — a registered prompt-template version.
export interface PromptVersion {
  id: number;
  agent_role: string;
  version_label: string;
  template: string;
  template_hash: string;
  description?: string | null;
  created_at: string;
  is_active: boolean;
}

// models/domain/prompt.py :: InstructionType (StrEnum).
export type InstructionType = 'intention' | 'knowledgeability' | 'commitment' | 'focus' | 'venue' | 'calibration';

// models/domain/prompt.py :: PromptInstruction — (type, label) is the natural key.
export interface PromptInstruction {
  id: number;
  type: InstructionType | null;
  label: string;
  instruction: string;
  description?: string | null;
  agent_role?: string | null;
  run_id?: string | null;
  created_at: string;
  is_active: boolean;
}

// models/controller/prompt.py :: PromptVersionListResponse / PromptInstructionListResponse.
export interface PromptVersionListResponse {
  prompts: PromptVersion[];
}

export interface PromptInstructionListResponse {
  instructions: PromptInstruction[];
}

// models/controller/prompt.py :: CreatePromptRequest / PromptVersionResponse.
export interface CreatePromptRequest {
  agent_role: string;
  version_label: string;
  template: string;
  description?: string | null;
}

export interface PromptVersionResponse {
  prompt: PromptVersion;
}

// models/controller/prompt.py :: UpdatePromptRequest / UpdateInstructionRequest —
// versions and instructions are immutable, only the metadata may change.
export interface UpdatePromptRequest {
  description?: string | null;
  is_active?: boolean | null;
}

export interface UpdateInstructionRequest {
  description?: string | null;
  is_active?: boolean | null;
}

// models/controller/prompt.py :: CreateInstructionRequest / PromptInstructionResponse.
export interface CreateInstructionRequest {
  type: InstructionType;
  label: string;
  instruction: string;
  description?: string | null;
  agent_role?: string | null;
  run_id?: string | null;
}

export interface PromptInstructionResponse {
  instruction: PromptInstruction;
}

// models/controller/prompt.py :: PromptPreviewRequest / PromptPreviewResponse.
export interface PromptPreviewRequest {
  agent_role: string;
  base_prompt_version: string;
  instruction_labels: string[];
}

export interface PromptPreviewResponse {
  prompt: string;
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
// Backend contract for compile/invoke — mirrors models/domain/graph.py:
// per-reviewer AgentConfig list, prompt composed on the BE from
// system_prompt_request. The FE GraphConfig maps onto this when launching.
// ---------------------------------------------------------------------------

// models/domain/graph.py :: AgentConfig (BE side).
export interface BackendAgentConfig {
  model: string;
  temperature: number;
  system_prompt_request: AgentSystemPromptRequest | null;
  request_context: AgentRequestContext;
}

// models/domain/graph.py :: GraphReviewConfig — committee size is reviewers.length.
export interface GraphReviewConfig {
  reviewers: BackendAgentConfig[];
  meta_reviewer: BackendAgentConfig;
  area_chair: BackendAgentConfig;
  author: BackendAgentConfig;
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

// models/domain/run_record.py :: AgentResponseRecord — one agent invocation:
// identity (role/index/round), the structured payload and the verbatim trace.
export interface AgentResponseRecord {
  round: number;
  agent_role: AgentRole;
  agent_index?: number | null;
  model?: string | null;
  response_payload: Record<string, unknown>;
  input_message?: string | null;
  context_used?: string | null;
  system_prompt?: string | null;
  input_tokens?: number | null;
  output_tokens?: number | null;
  total_tokens?: number | null;
  latency_seconds?: number | null;
}

// models/domain/run_record.py :: GraphReviewRecord — the full run record;
// agent_records/graph_config optional for defensiveness on legacy payloads.
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
  graph_config?: GraphReviewConfig;
  agent_records?: AgentResponseRecord[];
}
