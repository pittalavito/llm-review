"""Unit tests for the DB store seams (domain/store/db/store.py): the pure
row <-> domain translations, Adapter (rows -> domain models, reads) and Factory
(domain models -> rows, writes). No database involved."""
from models.domain.agent import AgentRole
from models.domain.paper import Paper, PaperType
from models.domain.prompt import PromptVersion
from models.domain.run_record import AgentResponseRecord, GraphReviewRecord
from models.store.db import (
    PaperTable,
    PromptVersionTable,
    ReviewAgentRunPayloadTable,
    ReviewAgentRunTable,
    ReviewRunPayloadTable,
    ReviewRunTable,
)
from domain.store.db.store import Adapter, Factory


class Utils:
    """Static builders for DB rows / domain models used across the tests."""

    @staticmethod
    def paper_row() -> PaperTable:
        return PaperTable(
            id=7, paper_id="open_review_p_pdf", paper_name="p.pdf", paper_type="OPEN_REVIEW",
            open_review_id="OR1", conference="ICLR", openreview_api_version="v2",
            human_decision="accept", num_graph_review=3,
        )

    @staticmethod
    def paper() -> Paper:
        return Paper(
            paper_id="open_review_p_pdf", paper_name="p.pdf", paper_type=PaperType.OPEN_REVIEW,
            open_review_id="OR1", conference="ICLR", openreview_api_version="v2",
            human_decision="accept", num_graph_review=3,
        )

    @staticmethod
    def run_record() -> GraphReviewRecord:
        return GraphReviewRecord(
            run_id="RID", timestamp="2026-01-01", paper_id="other_p_pdf", run_description="d",
            decision="accept", total_rounds=2, reviews=["r1"], meta_review={"overall_score": 7},
            area_chair_response={"decision": "accept"}, author_response={"rebuttal": "ok"},
            retrieval_metadata={"k": 1}, graph_config={"max_rounds": 3},
            agent_runs=[Utils.agent_run()],
        )

    @staticmethod
    def agent_run() -> AgentResponseRecord:
        return AgentResponseRecord(
            agent_role=AgentRole.REVIEWER, agent_index=1, round=0, input_message="m", context_used="c",
            response_payload={"rating": 6, "confidence": 4, "recommendation": "minor_revision"},
            input_tokens=100, output_tokens=50, total_tokens=150,
            system_prompt="You are reviewer 1.",
        )


class TestAdapter:
    def test_to_paper_maps_fields(self):
        paper = Adapter.to_paper(Utils.paper_row())
        assert paper.paper_type is PaperType.OPEN_REVIEW
        assert paper.paper_id == "open_review_p_pdf"
        assert paper.human_decision == "accept"
        assert paper.num_graph_review == 3
        assert paper.open_review_id == "OR1"

    def test_to_prompt_is_field_for_field(self):
        row = PromptVersionTable(
            id=1, agent_role="reviewer", version_label="v1", template="T",
            template_hash="h", description="d", created_at="2026-01-01", is_active=True,
        )
        prompt = Adapter.to_prompt(row)
        assert isinstance(prompt, PromptVersion)
        assert (prompt.id, prompt.agent_role, prompt.version_label, prompt.template_hash) == (1, "reviewer", "v1", "h")

    def test_to_run_summary_keeps_facts_only(self):
        row = ReviewRunTable(run_id="R1", timestamp="t", paper_id="other_p_pdf", decision="accept", total_rounds=2)
        summary = Adapter.to_run_summary(row)
        assert (summary.run_id, summary.decision, summary.total_rounds) == ("R1", "accept", 2)

    def test_to_run_record_reassembles_payload_and_agents(self):
        run_row = ReviewRunTable(run_id="R1", timestamp="t", paper_id="other_p_pdf", decision="accept", total_rounds=2)
        payload = ReviewRunPayloadTable(
            run_id="R1", reviews=["rev"], meta_review={"overall_score": 7},
            area_chair_response={"decision": "accept"}, author_response={"rebuttal": "x"},
            retrieval_metadata={"k": 1}, graph_config={"max_rounds": 3},
        )
        agent_row = ReviewAgentRunTable(id=1, run_id="R1", agent_role="reviewer", agent_index=1, round=0, input_message="m", context_used="c")
        agent_payload = ReviewAgentRunPayloadTable(agent_run_id=1, response_payload={"rating": 6})
        record = Adapter.to_run_record(run_row, payload, [agent_row], {1: agent_payload})
        assert record.reviews == ["rev"]
        assert record.graph_config == {"max_rounds": 3}
        assert len(record.agent_runs) == 1
        assert record.agent_runs[0].agent_role is AgentRole.REVIEWER and record.agent_runs[0].agent_index == 1
        assert record.agent_runs[0].response_payload == {"rating": 6}

    def test_to_run_record_degrades_when_payload_missing(self):
        run_row = ReviewRunTable(run_id="R1", timestamp="t", paper_id="other_p_pdf", decision=None, total_rounds=0)
        record = Adapter.to_run_record(run_row, None, [], {})
        assert record.reviews is None
        assert record.meta_review is None
        assert record.graph_config == {}
        assert record.agent_runs == []

    def test_to_agent_run_missing_payload_yields_empty_payload(self):
        row = ReviewAgentRunTable(id=2, run_id="R1", agent_role="meta_reviewer", round=1, input_message="m")
        agent_run = Adapter.to_agent_run(row, None)
        assert agent_run.agent_role is AgentRole.META_REVIEWER and agent_run.agent_index is None
        assert agent_run.response_payload == {}
        assert agent_run.response_schema is None  # only available in-process


class TestFactory:
    def test_to_paper_row_derives_id_and_unwraps_enum(self):
        row = Factory.to_paper_row(Utils.paper())
        assert row.paper_type == "OPEN_REVIEW"  # enum -> str value
        assert row.paper_id == "open_review_p_pdf"  # derived from type + file name
        assert row.human_decision == "accept"
        assert row.num_graph_review == 3
        assert row.id is None  # DB-generated

    def test_to_run_row_extracts_max_rounds_and_meta_score(self):
        row = Factory.to_run_row(Utils.run_record())
        assert row.run_id == "RID"
        assert row.max_rounds == 3  # from graph_config
        assert row.meta_overall_score == 7  # from meta_review payload

    def test_to_run_row_meta_score_none_when_no_meta(self):
        record = Utils.run_record()
        record.meta_review = None
        assert Factory.to_run_row(record).meta_overall_score is None

    def test_to_run_payload_row_is_verbatim(self):
        row = Factory.to_run_payload_row(Utils.run_record())
        assert row.reviews == ["r1"]
        assert row.meta_review == {"overall_score": 7}
        assert row.graph_config == {"max_rounds": 3}

    def test_to_agent_row_extracts_analytics_from_payload_and_record(self):
        row = Factory.to_agent_row("RID", Utils.agent_run())
        assert row.agent_role == "reviewer" and row.agent_index == 1
        assert (row.rating, row.confidence) == (6, 4)
        assert row.decision == "minor_revision"  # falls back to recommendation
        assert (row.input_tokens, row.output_tokens, row.total_tokens) == (100, 50, 150)
        assert row.latency_ms is None  # no runtime trace anymore

    def test_to_agent_row_prefers_decision_over_recommendation(self):
        agent_run = Utils.agent_run()
        agent_run.response_payload = {"decision": "accept", "recommendation": "minor_revision"}
        assert Factory.to_agent_row("RID", agent_run).decision == "accept"

    def test_to_agent_payload_row_carries_payload_and_system_prompt(self):
        row = Factory.to_agent_payload_row(Utils.agent_run())
        assert row.response_payload["rating"] == 6
        assert row.prompt_trace == {"system_prompt": "You are reviewer 1."}
        assert row.runtime_trace is None

    def test_to_agent_pairs_builds_one_pair_per_run(self):
        pairs = Factory.to_agent_pairs("RID", [Utils.agent_run(), Utils.agent_run()])
        assert len(pairs) == 2
        facts, payload = pairs[0]
        assert isinstance(facts, ReviewAgentRunTable)
        assert isinstance(payload, ReviewAgentRunPayloadTable)
        assert facts.run_id == "RID"
