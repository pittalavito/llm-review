"""Unit tests for the DB store seams (domain/store/db/store.py): the pure
row <-> domain translations, Adapter (rows -> domain models, reads) and Factory
(domain models -> rows, writes), including the derivation of the run-level
responses from the agent traces. No database involved."""
from models.domain.agent import AgentRole
from models.domain.paper import Author, Paper, PaperType
from models.domain.prompt import PromptVersion, SystemPromptPreset
from models.domain.run_record import AgentResponseRecord, GraphReviewRecord
from models.store.db import (
    AgentTraceTable,
    AuthorTable,
    GraphReviewAgentTable,
    GraphReviewTable,
    PaperTable,
    PromptVersionTable,
    SystemPromptPresetTable,
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
            run_id="RID", timestamp="2026-01-01", paper_id="other_p_pdf", description="d",
            decision="accept", total_rounds=2, reviews_response=[{"rating": 6}],
            meta_review_response={"overall_score": 7},
            area_chair_response={"decision": "accept"}, author_response={"rebuttal": "ok"},
            graph_config={"max_rounds": 3},
            agent_records=[Utils.agent_record()],
        )

    @staticmethod
    def agent_record(role: AgentRole = AgentRole.REVIEWER, index: int | None = 1, payload: dict | None = None) -> AgentResponseRecord:
        return AgentResponseRecord(
            agent_role=role, agent_index=index, round=0, input_message="m", context_used="c",
            response_payload=payload or {"rating": 6, "confidence": 4, "recommendation": "minor_revision"},
            input_tokens=100, output_tokens=50, total_tokens=150,
            system_prompt="You are reviewer 1.",
            prompt_preset_id=2,
        )


class TestAdapter:
    def test_to_paper_maps_fields(self):
        paper = Adapter.to_paper(Utils.paper_row())
        assert paper.paper_type is PaperType.OPEN_REVIEW
        assert paper.paper_id == "open_review_p_pdf"
        assert paper.human_decision == "accept"
        assert paper.num_graph_review == 3
        assert paper.open_review_id == "OR1"

    def test_to_author_maps_fields_and_link_position(self):
        row = AuthorTable(
            id=3, full_name="Ada Lovelace", email="ada@ex.org",
            affiliation="Analytical Engines", openreview_profile_id="~Ada_Lovelace1",
        )
        author = Adapter.to_author(row, position=2)
        assert (author.id, author.full_name, author.email) == (3, "Ada Lovelace", "ada@ex.org")
        assert (author.affiliation, author.openreview_profile_id) == ("Analytical Engines", "~Ada_Lovelace1")
        assert author.position == 2

    def test_to_author_without_link_has_no_position(self):
        author = Adapter.to_author(AuthorTable(id=1, full_name="X"))
        assert author.position is None

    def test_to_authors_keeps_link_order(self):
        pairs = [(AuthorTable(id=1, full_name="A"), 1), (AuthorTable(id=2, full_name="B"), 2)]
        authors = Adapter.to_authors(pairs)
        assert [(a.full_name, a.position) for a in authors] == [("A", 1), ("B", 2)]

    def test_to_prompt_is_field_for_field(self):
        row = PromptVersionTable(
            id=1, agent_role="reviewer", version_label="v1", template="T",
            template_hash="h", description="d", created_at="2026-01-01", is_active=True,
        )
        prompt = Adapter.to_prompt(row)
        assert isinstance(prompt, PromptVersion)
        assert (prompt.id, prompt.agent_role, prompt.version_label, prompt.template_hash) == (1, "reviewer", "v1", "h")

    def test_to_preset_is_field_for_field(self):
        row = SystemPromptPresetTable(
            id=4, agent_role="reviewer", name="severo", description="d",
            base_prompt_version="v1", instruction_ids=[3, 7],
            created_at="2026-01-01", updated_at="2026-02-01", is_active=True,
        )
        preset = Adapter.to_preset(row)
        assert isinstance(preset, SystemPromptPreset)
        assert (preset.id, preset.agent_role, preset.name, preset.base_prompt_version) == (4, "reviewer", "severo", "v1")
        assert preset.instruction_ids == [3, 7]
        assert (preset.created_at, preset.updated_at, preset.is_active) == ("2026-01-01", "2026-02-01", True)

    def test_to_run_summary_keeps_facts_and_analytics(self):
        row = GraphReviewTable(
            run_id="R1", timestamp="t", paper_id="other_p_pdf", description="d",
            decision="accept", total_rounds=2, max_rounds=3, meta_overall_score=7,
        )
        summary = Adapter.to_run_summary(row)
        assert (summary.run_id, summary.decision, summary.total_rounds) == ("R1", "accept", 2)
        assert summary.description == "d"
        assert (summary.max_rounds, summary.meta_overall_score) == (3, 7)

    def test_to_run_record_derives_responses_from_agent_rows(self):
        run_row = GraphReviewTable(
            run_id="R1", timestamp="t", paper_id="other_p_pdf", description="d",
            decision="accept", total_rounds=1, graph_config={"max_rounds": 3},
        )
        rows = [
            GraphReviewAgentTable(id=1, run_id="R1", agent_role="reviewer", agent_index=1, round=0, agent_trace_id=11, response_payload={"rating": 6}),
            GraphReviewAgentTable(id=2, run_id="R1", agent_role="reviewer", agent_index=2, round=0, agent_trace_id=12, response_payload={"rating": 5}),
            GraphReviewAgentTable(id=3, run_id="R1", agent_role="meta_reviewer", round=1, agent_trace_id=13, response_payload={"overall_score": 7}),
            GraphReviewAgentTable(id=4, run_id="R1", agent_role="area_chair", round=0, agent_trace_id=14, response_payload={"decision": "accept"}),
        ]
        traces = {
            11: AgentTraceTable(id=11, run_id="R1", input_message="m1", response_payload={"rating": 6}),
            12: AgentTraceTable(id=12, run_id="R1", input_message="m2", response_payload={"rating": 5}),
            13: AgentTraceTable(id=13, run_id="R1", response_payload={"overall_score": 7}),
            14: AgentTraceTable(id=14, run_id="R1", response_payload={"decision": "accept"}),
        }
        record = Adapter.to_run_record(run_row, rows, traces)
        # derived, in insertion order — one entry per reviewer invocation
        assert record.reviews_response == [{"rating": 6}, {"rating": 5}]
        assert record.meta_review_response == {"overall_score": 7}
        assert record.area_chair_response == {"decision": "accept"}
        assert record.author_response is None  # role never ran
        assert record.graph_config == {"max_rounds": 3}
        assert len(record.agent_records) == 4
        assert record.agent_records[0].input_message == "m1"  # trace still feeds the verbatim fields

    def test_to_run_record_singleton_roles_take_the_last_round(self):
        run_row = GraphReviewTable(run_id="R1", timestamp="t", paper_id="p", decision=None, total_rounds=2)
        rows = [
            GraphReviewAgentTable(id=1, run_id="R1", agent_role="meta_reviewer", round=1, agent_trace_id=21, response_payload={"overall_score": 5}),
            GraphReviewAgentTable(id=2, run_id="R1", agent_role="meta_reviewer", round=2, agent_trace_id=22, response_payload={"overall_score": 8}),
        ]
        traces = {
            21: AgentTraceTable(id=21, run_id="R1", response_payload={"overall_score": 5}),
            22: AgentTraceTable(id=22, run_id="R1", response_payload={"overall_score": 8}),
        }
        record = Adapter.to_run_record(run_row, rows, traces)
        assert record.meta_review_response == {"overall_score": 8}  # last round wins

    def test_to_run_record_degrades_without_agents(self):
        run_row = GraphReviewTable(run_id="R1", timestamp="t", paper_id="other_p_pdf", decision=None, total_rounds=0)
        record = Adapter.to_run_record(run_row, [], {})
        assert record.reviews_response is None
        assert record.meta_review_response is None
        assert record.graph_config == {}
        assert record.agent_records == []

    def test_to_agent_record_missing_trace_yields_empty_payload(self):
        row = GraphReviewAgentTable(id=2, run_id="R1", agent_role="meta_reviewer", round=1)
        agent_record = Adapter.to_agent_record(row, None)
        assert agent_record.agent_role is AgentRole.META_REVIEWER and agent_record.agent_index is None
        assert agent_record.response_payload == {}
        assert agent_record.system_prompt is None

    def test_agent_record_round_trip_is_lossless(self):
        # write side -> rows -> read side: identity from the agent row, trace verbatim
        original = Utils.agent_record()
        row = Factory.to_agent_record_row("RID", original)
        row.id = 1
        trace = Factory.to_agent_trace_row("RID", original)
        restored = Adapter.to_agent_record(row, trace)
        assert restored == original


class TestFactory:
    def test_to_paper_row_generates_uid_id_and_unwraps_enum(self):
        row = Factory.to_paper_row(Utils.paper(), "pdf")
        assert row.paper_type == "OPEN_REVIEW"  # enum -> str value
        assert row.paper_id.endswith("_pdf")  # format suffix for the files store
        assert len(row.paper_id) == 32 + len("_pdf")  # uuid4 hex + suffix
        assert row.paper_name == "p.pdf"  # name travels untouched
        assert row.human_decision == "accept"
        assert row.num_graph_review == 3
        assert row.id is None  # DB-generated

    def test_to_paper_row_ids_are_unique(self):
        first = Factory.to_paper_row(Utils.paper(), "pdf")
        second = Factory.to_paper_row(Utils.paper(), "pdf")
        assert first.paper_id != second.paper_id

    def test_to_author_row_drops_position_and_id(self):
        author = Author(
            id=9, full_name="Ada Lovelace", email="ada@ex.org",
            affiliation="Analytical Engines", openreview_profile_id="~Ada_Lovelace1", position=1,
        )
        row = Factory.to_author_row(author)
        assert (row.full_name, row.email, row.affiliation) == ("Ada Lovelace", "ada@ex.org", "Analytical Engines")
        assert row.openreview_profile_id == "~Ada_Lovelace1"
        assert row.id is None  # DB-generated, never copied from the domain model

    def test_to_run_row_extracts_analytics_and_keeps_config(self):
        row = Factory.to_run_row(Utils.run_record())
        assert row.run_id == "RID"
        assert row.description == "d"
        assert row.max_rounds == 3  # from graph_config
        assert row.meta_overall_score == 7  # from the meta-review payload
        assert row.graph_config == {"max_rounds": 3}

    def test_to_run_row_meta_score_none_when_no_meta(self):
        record = Utils.run_record()
        record.meta_review_response = None
        assert Factory.to_run_row(record).meta_overall_score is None

    def test_to_agent_record_row_extracts_analytics_only(self):
        row = Factory.to_agent_record_row("RID", Utils.agent_record())
        assert row.agent_role == "reviewer" and row.agent_index == 1
        assert (row.rating, row.confidence) == (6, 4)
        assert row.decision == "minor_revision"  # falls back to recommendation
        assert row.agent_trace_id is None  # linked by the repository at save time
        assert row.prompt_preset_id == 2  # the prompt itself lives only in the trace
        assert not hasattr(row, "system_prompt")

    def test_to_agent_record_row_prefers_decision_over_recommendation(self):
        agent_record = Utils.agent_record(payload={"decision": "accept", "recommendation": "minor_revision"})
        assert Factory.to_agent_record_row("RID", agent_record).decision == "accept"

    def test_to_agent_trace_row_is_verbatim(self):
        trace = Factory.to_agent_trace_row("RID", Utils.agent_record())
        assert trace.run_id == "RID"
        assert trace.input_message == "m"
        assert trace.system_prompt == "You are reviewer 1."
        assert trace.response_payload["rating"] == 6
        assert (trace.input_tokens, trace.output_tokens, trace.total_tokens) == (100, 50, 150)
        assert trace.latency_seconds is None  # reserved, not populated yet

    def test_to_run_rows_bundles_everything_for_save(self):
        run_row, pairs = Factory.to_run_rows(Utils.run_record())
        assert isinstance(run_row, GraphReviewTable) and run_row.run_id == "RID"
        assert len(pairs) == 1
        agent_row, trace_row = pairs[0]
        assert isinstance(agent_row, GraphReviewAgentTable)
        assert isinstance(trace_row, AgentTraceTable)
        assert agent_row.run_id == "RID" and trace_row.run_id == "RID"
