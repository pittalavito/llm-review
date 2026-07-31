from pydantic import Base64Bytes, BaseModel, Field

from models.domain.chat import ChatModelName
from models.domain.graph import ReviewGraphConfig
from models.domain.paper import Paper
from models.domain.retrieval import RagStrategy

class ChatRequest(BaseModel):
    """Basic chat request: model, temperature and the message — nothing else."""
    model: ChatModelName
    temperature: float = Field(default=0.0, ge=0, le=2)
    message: str = "Respond with a simple 'ping' message."


class ChatResponse(BaseModel):
    """Full chat response returned to the FE as JSON: the model's payload
    (JSON-serialized) plus the token usage and any structured-output parsing
    error. ``response`` is None only when the invocation produced no payload."""
    response: str | None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    parsing_error: str | None = None
    
    
class CreatePaperRequest(BaseModel):
    """Request model for creating a new paper. ``file_bytes`` travels as a
    base64 string in the JSON body (raw bytes would not survive UTF-8) and is
    decoded to raw bytes by pydantic."""
    paper: Paper
    file_bytes: Base64Bytes = Field(..., description="The paper's file content, base64-encoded.")


class CreatePaperResponse(Paper):
    """Response model for creating a new paper."""


class IndexPaperRequest(BaseModel):
    """Request model for indexing a paper for retrieval."""
    paper_id: str
    strategy: RagStrategy
    strategy_version: str = "v1"
    force: bool = False


class IndexPaperAccepted(BaseModel):
    """202 response: the indexing runs in background; poll the status endpoint
    with the same (paper_id, strategy, strategy_version) to know when done."""
    status: str = "accepted"
    paper_id: str
    strategy: RagStrategy
    strategy_version: str

class CreateGraphReviewRequest(BaseModel):
    """Request to run the review graph on a paper with a given configuration."""
    paper_id: str
    graph_config: ReviewGraphConfig
    run_description: str = ""


class CompiledAgentInfo(BaseModel):
    """Identity of one agent in the compiled committee."""
    agent_role: str
    agent_index: int | None = None


class CompileGraphResponse(BaseModel):
    """The compiled committee, keyed by agent name (``reviewer_1``…)."""
    agents: dict[str, CompiledAgentInfo]
    
    @classmethod
    def from_agents(cls, agents: dict[str, CompiledAgentInfo]) -> "CompileGraphResponse":
        """Construct a CompileGraphResponse from a dict of agent names to CompiledAgentInfo."""
        return cls(agents={
            name: CompiledAgentInfo(agent_role=str(agent.agent_role), agent_index=agent.agent_index)
            for name, agent in agents.items()
        })