"""Request/response models for the /graph endpoints. The request body
(CreateGraphReviewRequest) is the service-layer command object and lives in
``models.domain.graph``."""
from pydantic import BaseModel

from models.domain.graph import GraphReviewConfig
from models.domain.run_record import GraphReviewRecord, GraphReviewSummary

class CreateGraphReviewRequest(BaseModel):
    """Request to run the review graph on a paper with a given configuration."""
    paper_id: str
    graph_config: GraphReviewConfig
    description: str = "" 
    
    @classmethod
    def from_domain(cls, request: "CreateGraphReviewRequest") -> "CreateGraphReviewRequest":
        """Construct a CreateGraphReviewRequest from a domain-level request."""
        return cls(
            paper_id=request.paper_id,
            graph_config=request.graph_config,
            description=request.description
        )


class GraphReviewConfigResponse(BaseModel):
    """Response containing the current graph configuration."""
    graph_config: GraphReviewConfig

    @classmethod
    def from_response(cls, graph_config: GraphReviewConfig) -> "GraphReviewConfigResponse":
        """Construct a GraphReviewConfigResponse from a GraphReviewConfig."""
        return cls(graph_config=graph_config)


class GraphReviewRecordResponse(BaseModel):
    """Response containing the record of a graph review run."""
    record: GraphReviewRecord

    @classmethod
    def from_response(cls, record: GraphReviewRecord) -> "GraphReviewRecordResponse":
        """Construct a GraphReviewRecordResponse from a GraphReviewRecord."""
        return cls(record=record)


class GraphReviewSummaryResponse(BaseModel):
    """Response containing the run-history summaries."""
    summaries: list[GraphReviewSummary]

    @classmethod
    def from_response(cls, summaries: list[GraphReviewSummary]) -> "GraphReviewSummaryResponse":
        """Construct a GraphReviewSummaryResponse from a list of GraphReviewSummary."""
        return cls(summaries=summaries)

