from pydantic import BaseModel

from domain.models.agent import AgentRole


class AgentRun(BaseModel):
    """Complete trace of a single agent invocation."""

    agent_role: AgentRole
    agent_index: int | None = None
    round: int
    input_message: str
    context_used: str | None
    response_payload: dict
    prompt_trace: dict | None = None
    runtime_trace: dict | None = None


class GraphReviewRecord(BaseModel):
    """Complete record of a single review-graph execution."""

    run_id: str
    timestamp: str
    paper_id: str
    run_description: str | None = None
    decision: str | None
    total_rounds: int
    reviews: list[str] | None = None
    meta_review: dict | None
    area_chair_response: dict | None = None
    author_response: dict | None
    retrieval_metadata: dict | None
    graph_config: dict
    agent_runs: list[AgentRun]


class GraphReviewSummary(BaseModel):
    """Lightweight version of RunRecord for the run-history list."""

    run_id: str
    timestamp: str
    paper_id: str
    run_description: str | None = None
    decision: str | None
    total_rounds: int
