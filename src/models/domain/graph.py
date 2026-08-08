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
    prompt_preset_id: int
    request_context: AgentRequestContext = AgentRequestContext.default_none_context()


class GraphReviewConfig(BaseModel):
    """Full configuration of one review-graph run: an AgentConfig per reviewer
    (each with its own prompt/persona), one per single-instance role, and the
    revision rounds. The committee size is ``len(reviewers)``."""
    reviewers: list[AgentConfig] = Field(min_length=1)
    meta_reviewer: AgentConfig
    area_chair: AgentConfig
    author: AgentConfig
    max_rounds: int = Field(default=1, ge=1, le=5)

    @property
    def num_reviewers(self) -> int:
        return len(self.reviewers)

    @staticmethod
    def default_config(num_reviewers: int = 1, max_rounds: int = 1) -> "GraphReviewConfig":
        """A mock-backed default (every role on the mock model) for smoke runs/tests."""
        def cfg() -> AgentConfig:
            return AgentConfig(model=ChatModelName.MOCK, temperature=0.0, prompt_preset_id=0)
        return GraphReviewConfig(
            reviewers=[cfg() for _ in range(num_reviewers)],
            meta_reviewer=cfg(),
            area_chair=cfg(),
            author=cfg(),
            max_rounds=max_rounds
        )


class CreateGraphReviewRequest(BaseModel):
    """Request to run the review graph on a paper with a given configuration."""
    paper_id: str
    graph_config: GraphReviewConfig
    description: str = ""