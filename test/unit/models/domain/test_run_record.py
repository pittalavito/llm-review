"""Unit tests for GraphReviewRecord.from_result (models/domain/run_record.py):
the mapping from the final LangGraph ReviewState dict to the persistable
record. This pins the stringly-typed state-key contract (agent_records,
reviews_response, meta_review_response, ...) shared with domain/graph."""
from models.domain.agent import AgentRole
from models.domain.graph import CreateGraphReviewRequest, ReviewGraphConfig
from models.domain.run_record import AgentResponseRecord, GraphReviewRecord


def _request(description: str = "una prova") -> CreateGraphReviewRequest:
    return CreateGraphReviewRequest(
        paper_id="other_p_pdf",
        graph_config=ReviewGraphConfig.default_config(num_reviewers=2, max_rounds=3),
        description=description,
    )


def _final_state() -> dict:
    agent_record = AgentResponseRecord(
        round=0, agent_role=AgentRole.REVIEWER, agent_index=1,
        response_payload={"rating": 6}, input_message="m", system_prompt="sp",
    )
    return {
        "paper_id": "other_p_pdf",
        "reviews_response": [{"rating": 6}, {"rating": 5}],
        "meta_review_response": {"overall_score": 7},
        "area_chair_response": {"decision": "accept"},
        "decision": "accept",
        "author_response": None,
        "revised_sections": None,
        "current_round": 2,
        "max_rounds": 3,
        "agent_records": [agent_record.model_dump()],
    }


class TestFromResult:
    def test_maps_state_keys_and_request_fields(self):
        record = GraphReviewRecord.from_result(_final_state(), _request(), run_id="RID")
        assert record.run_id == "RID"
        assert record.paper_id == "other_p_pdf"
        assert record.description == "una prova"
        assert record.decision == "accept"
        assert record.total_rounds == 2  # from current_round
        assert record.reviews_response == [{"rating": 6}, {"rating": 5}]
        assert record.meta_review_response == {"overall_score": 7}
        assert record.graph_config["max_rounds"] == 3
        assert record.timestamp  # stamped here

    def test_agent_records_are_validated_back_into_models(self):
        record = GraphReviewRecord.from_result(_final_state(), _request(), run_id="RID")
        assert len(record.agent_records) == 1
        agent_record = record.agent_records[0]
        assert isinstance(agent_record, AgentResponseRecord)
        assert agent_record.agent_role is AgentRole.REVIEWER
        assert agent_record.system_prompt == "sp"

    def test_empty_state_degrades_to_defaults(self):
        record = GraphReviewRecord.from_result({}, _request(description=""), run_id="RID")
        assert record.description is None  # empty string collapses to None
        assert record.decision is None
        assert record.total_rounds == 0
        assert record.agent_records == []
        assert record.reviews_response is None
