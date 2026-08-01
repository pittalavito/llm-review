"""Unit tests for the StoreService facade (service/store_service.py).

The repositories (which would open real Postgres/Redis connections in their
constructors) are replaced with in-memory fakes via monkeypatch, so the test
exercises the orchestration and the *real* Adapter/Factory translation seams
without any infrastructure."""
import pytest

import service.store_service as store_service_mod
from models.domain.agent import AgentRole
from models.domain.paper import Paper, PaperType
from models.domain.retrieval import IndexInfo, RagIndex
from models.domain.run_record import AgentResponseRecord, GraphReviewRecord, GraphReviewSummary
from models.store.db import (
    PaperTable,
    ReviewAgentRunPayloadTable,
    ReviewAgentRunTable,
    ReviewRunPayloadTable,
    ReviewRunTable,
)
from models.store.redis import OpenReviewCache as StoreOpenReviewCache, RagIndex as StoreRagIndex
from service.store_service import StoreService


def _store_rag_index() -> StoreRagIndex:
    return StoreRagIndex.model_validate({
        "doc_id": "d1", "paper_id": "other_p_pdf",
        "file_signature": {"mtime_ns": 1, "size": 2},
        "settings": {"strategy_version": "v1"},
        "sections": [{"name": "Intro", "text": "hello"}, {"name": "Methods", "text": "world"}],
    })


def _review_note() -> dict:
    return {
        "id": "n1", "invitation": "ICLR/-/Official_Review", "signatures": ["ICLR/Reviewer_abc"],
        "content": {"summary_of_the_paper": "S", "rating": "6: ok", "confidence": "4: confident"},
    }


class FakeResults:
    """Stand-in for DbResultRepository."""
    saved: dict = {}

    def __init__(self):
        pass

    def save_rows(self, run_row, payload_row, agent_pairs):
        FakeResults.saved = {"run_row": run_row, "payload_row": payload_row, "agent_pairs": agent_pairs}
        return "RID-123"

    def list_summaries(self):
        return [ReviewRunTable(run_id="R1", timestamp="t", paper_id="other_p_pdf", decision="accept", total_rounds=1)]

    def get_rows(self, run_id):
        if run_id == "missing":
            return None
        run_row = ReviewRunTable(run_id=run_id, timestamp="t", paper_id="other_p_pdf", decision="accept", total_rounds=2)
        payload = ReviewRunPayloadTable(run_id=run_id, reviews=["rev"], meta_review={"overall_score": 7}, graph_config={"max_rounds": 3})
        agent_row = ReviewAgentRunTable(id=1, run_id=run_id, agent_role="reviewer", agent_index=1, round=0, input_message="m")
        agent_payload = ReviewAgentRunPayloadTable(agent_run_id=1, response_payload={"rating": 6})
        return (run_row, payload, [agent_row], {1: agent_payload})

    @staticmethod
    def build_run_id(paper_id):
        return "built:" + paper_id


class FakePapers:
    """Stand-in for DbPaperRepository."""
    created = None

    def __init__(self):
        pass

    def list(self):
        return [PaperTable(id=1, paper_id="other_p_pdf", paper_name="P", paper_type="OTHER")]

    def get_by_id(self, paper_id):
        if paper_id == "missing":
            return None
        return PaperTable(id=2, paper_id=paper_id, paper_name="Q", paper_type="OPEN_REVIEW", human_decision="accept", num_graph_review=3)

    def create(self, row):
        FakePapers.created = row
        row.id = 99
        return row


class FakePrompts:
    """Stand-in for DbPromptRepository (constructor + seed only — not exercised here)."""

    def __init__(self):
        pass

    def seed_defaults(self, seeds) -> int:
        return 0


class FakeRagIndex:
    """Stand-in for RedisRagIndexRepository."""
    saved = None

    def __init__(self):
        pass

    def load(self, doc_id):
        return None if doc_id == "missing" else _store_rag_index()

    def save(self, record):
        FakeRagIndex.saved = record

    @staticmethod
    def compute_doc_id(paper_id, strategy, strategy_version):
        return f"doc:{paper_id}:{strategy}:{strategy_version}"


class FakeCache:
    """Stand-in for RedisOpenReviewCacheRepository."""

    def __init__(self):
        pass

    def load(self, key):
        return None if key == "missing" else StoreOpenReviewCache.model_validate({"notes": [_review_note()]})


class FakeFiles:
    """Stand-in for FilePaperRepository (constructor only — not exercised here)."""

    def __init__(self):
        pass


@pytest.fixture
def service(monkeypatch) -> StoreService:
    monkeypatch.setattr(store_service_mod, "DbResultRepository", FakeResults)
    monkeypatch.setattr(store_service_mod, "DbPaperRepository", FakePapers)
    monkeypatch.setattr(store_service_mod, "DbPromptRepository", FakePrompts)
    monkeypatch.setattr(store_service_mod, "RedisRagIndexRepository", FakeRagIndex)
    monkeypatch.setattr(store_service_mod, "RedisOpenReviewCacheRepository", FakeCache)
    monkeypatch.setattr(store_service_mod, "FilePaperRepository", FakeFiles)
    return StoreService()


def _run_record() -> GraphReviewRecord:
    return GraphReviewRecord(
        run_id="RID", timestamp="t", paper_id="other_p_pdf", decision="accept", total_rounds=2,
        reviews_response=["r"], meta_review_response={"overall_score": 7}, author_response=None, retrieval_metadata=None,
        graph_config={"max_rounds": 3},
        agent_record=[AgentResponseRecord(agent_role=AgentRole.REVIEWER, agent_index=1, round=0, input_message="m", context_used=None, response_payload={"rating": 6})],
    )


class TestRuns:
    def test_save_run_applies_factory_and_returns_id(self, service):
        assert service.save_run(_run_record()) == "RID-123"
        run_row = FakeResults.saved["run_row"]
        assert isinstance(run_row, ReviewRunTable)
        assert run_row.max_rounds == 3 and run_row.meta_overall_score == 7  # Factory extracted these
        assert len(FakeResults.saved["agent_pairs"]) == 1

    def test_list_runs_maps_rows_to_summaries(self, service):
        summaries = service.list_runs()
        assert len(summaries) == 1 and isinstance(summaries[0], GraphReviewSummary)
        assert summaries[0].run_id == "R1"

    def test_get_run_returns_none_when_missing(self, service):
        assert service.get_run("missing") is None

    def test_get_run_builds_full_record_via_adapter(self, service):
        record = service.get_run("R1")
        assert isinstance(record, GraphReviewRecord)
        assert record.reviews_response == ["rev"]
        assert record.graph_config == {"max_rounds": 3}
        assert record.agent_record[0].agent_role is AgentRole.REVIEWER and record.agent_record[0].agent_index == 1
        assert record.agent_record[0].response_payload == {"rating": 6}

    def test_build_run_id_delegates_to_repository(self, service):
        assert service.build_run_id("other_p_pdf") == "built:other_p_pdf"


class TestPapers:
    def test_list_papers_catalog_maps_to_domain(self, service):
        papers = service.list_papers_catalog()
        assert len(papers) == 1 and isinstance(papers[0], Paper)
        assert papers[0].paper_type is PaperType.OTHER

    def test_get_paper_returns_none_when_missing(self, service):
        assert service.get_paper("missing") is None

    def test_get_paper_maps_row_fields(self, service):
        paper = service.get_paper("other_x_pdf")
        assert paper.human_decision == "accept"
        assert paper.num_graph_review == 3

    def test_create_paper_roundtrips_through_factory_and_adapter(self, service):
        result = service.create_paper(Paper(paper_id="ignored", paper_name="n.pdf", paper_type=PaperType.OTHER))
        assert isinstance(result, Paper)
        assert result.id == 99 and result.paper_id == "other_n_pdf"  # Factory derives the id from name+type
        assert FakePapers.created.paper_type == "OTHER"  # Factory unwrapped the enum


class TestRagIndex:
    def test_get_rag_index_maps_record(self, service):
        index = service.get_rag_index("d1")
        assert isinstance(index, RagIndex) and index.doc_id == "d1"

    def test_get_rag_index_none_when_missing(self, service):
        assert service.get_rag_index("missing") is None

    def test_save_rag_index_builds_store_record(self, service):
        service.save_rag_index(service.get_rag_index("d1"))
        assert isinstance(FakeRagIndex.saved, StoreRagIndex)
        assert FakeRagIndex.saved.doc_id == "d1"

    def test_get_index_info_and_full_text(self, service):
        info = service.get_index_info("d1")
        assert isinstance(info, IndexInfo) and info.section_count == 2
        assert service.get_full_paper_text("d1") == "# Intro\nhello\n\n# Methods\nworld"

    def test_compute_doc_id_delegates_to_repository(self, service):
        assert service.compute_doc_id("/p.pdf", "bm25", "v1") == "doc:/p.pdf:bm25:v1"


class TestOpenReview:
    def test_get_human_reviews_parses_cache_end_to_end(self, service):
        reviews = service.get_human_reviews("k")
        assert len(reviews) == 1
        assert reviews[0].reviewer_id == "Reviewer_abc"
        assert reviews[0].rating == 6

    def test_get_human_reviews_empty_when_cache_missing(self, service):
        assert service.get_human_reviews("missing") == []
