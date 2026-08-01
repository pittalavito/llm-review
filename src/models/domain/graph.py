"""Graph run configuration: one LLM config per role plus the committee size
(num_reviewers) and the revision-round cap. Persisted verbatim as the run's
``graph_config`` JSON; ``max_rounds`` is also mirrored into review_run."""
from pydantic import BaseModel, Field

from models.domain.chat import ChatModelName
from models.domain.agent import AgentRequestContext


class AgentConfig(BaseModel):
    """LLM settings for one agent role."""
    model: ChatModelName
    temperature: float = Field(default=0.4, ge=0.0, le=2.0)
    system_prompt: str = ""
    request_context: AgentRequestContext = AgentRequestContext.default_none_context()


class GraphReviewConfig(BaseModel):
    """Full configuration of one review-graph run: an AgentConfig per role, the
    number of reviewers on the committee (unbounded), and the revision rounds.
    The N reviewers share the single ``reviewer`` config (persona/focus deferred)."""
    reviewer: AgentConfig
    meta_reviewer: AgentConfig
    area_chair: AgentConfig
    author: AgentConfig
    num_reviewers: int = Field(default=3, ge=1)
    max_rounds: int = Field(default=1, ge=1, le=5)

    @staticmethod
    def default_config(num_reviewers: int = 1, max_rounds: int = 1) -> "GraphReviewConfig":
        """A mock-backed default (every role on the mock model) for smoke runs/tests."""
        def cfg() -> AgentConfig:
            return AgentConfig(model=ChatModelName.MOCK, temperature=0.4)
        return GraphReviewConfig(
            reviewer=cfg(), 
            meta_reviewer=cfg(), 
            area_chair=cfg(), 
            author=cfg(),
            num_reviewers=num_reviewers, 
            max_rounds=max_rounds
        )


class CreateGraphReviewRequest(BaseModel):
    """Request to run the review graph on a paper with a given configuration."""
    paper_id: str
    graph_config: GraphReviewConfig
    description: str = ""