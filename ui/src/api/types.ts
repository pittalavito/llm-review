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
  response: string;
  input_tokens: number | null;
  output_tokens: number | null;
  total_tokens: number | null;
  parsing_error: string | null;
}
