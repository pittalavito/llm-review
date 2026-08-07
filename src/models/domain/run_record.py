from pydantic import BaseModel
from datetime import datetime, timezone

from models.domain.agent import AgentResponse, AgentRole
from models.domain.chat import ToolCallRecord
from models.domain.graph import CreateGraphReviewRequest

class AgentResponseRecord(BaseModel):
    round: int
    agent_role: AgentRole
    agent_index: int | None = None
    model: str | None = None
    response_payload: dict
    input_message: str | None = None
    context_used: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    system_prompt: str | None = None
    prompt_preset_id: int | None = None
    latency_seconds: float | None = None
    tool_trace: list[ToolCallRecord] | None = None

    @classmethod
    def from_response(cls, response: AgentResponse, round: int) -> "AgentResponseRecord":
        """Live ``AgentResponse`` -> persistable record. ``round`` is computed by
        the caller (the graph node, which knows the state and its offset)."""
        return cls(
            round=round,
            agent_role=response.agent_role,
            agent_index=response.agent_index,
            model=str(response.model) if response.model is not None else None,
            response_payload=response.response_schema.model_dump(),
            input_message=response.input_message,
            context_used=response.context_used,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            total_tokens=response.total_tokens,
            system_prompt=response.system_prompt,
            prompt_preset_id=response.prompt_preset_id,
            latency_seconds=response.latency_seconds,
            tool_trace=response.tool_trace,
        )


class GraphReviewRecord(BaseModel):
    """Complete record of a single review-graph execution."""
    run_id: str
    timestamp: str
    paper_id: str
    description: str | None = None
    decision: str | None
    total_rounds: int
    graph_config: dict

    reviews_response: list[dict] | None = None
    meta_review_response: dict | None
    area_chair_response: dict | None = None
    author_response: dict | None

    agent_records: list[AgentResponseRecord]

    @classmethod
    def from_result(cls, result: dict, request: CreateGraphReviewRequest, run_id: str) -> "GraphReviewRecord":
        """Assemble a full record from a live graph result (the final
        ReviewState mapping — typed as dict to keep this shared-models layer
        free of domain.graph imports) and its request. ``run_id`` comes from the
        caller (only the store can mint one); the timestamp is stamped here."""
        agent_records = [AgentResponseRecord.model_validate(record) for record in result.get("agent_records", [])]
        return cls(
            run_id=run_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            paper_id=request.paper_id,
            description=request.description or None,
            decision=result.get("decision"),
            total_rounds=result.get("current_round", 0),
            reviews_response=result.get("reviews_response"),
            meta_review_response=result.get("meta_review_response"),
            area_chair_response=result.get("area_chair_response"),
            author_response=result.get("author_response"),
            graph_config=request.graph_config.model_dump(),
            agent_records=agent_records,
        )


class GraphReviewSummary(BaseModel):
    """Lightweight projection of GraphReviewRecord for the run-history list,
    plus the analytics facts extracted at save time."""

    run_id: str
    timestamp: str
    paper_id: str
    description: str | None = None
    decision: str | None
    total_rounds: int
    max_rounds: int | None = None
    meta_overall_score: int | None = None
