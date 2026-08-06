"""Unit tests for the StoreService facade (service/store_service.py).

The repositories (which would open real Postgres/Redis connections in their
constructors) are replaced with in-memory fakes via monkeypatch, so the test
exercises the orchestration and the *real* Adapter/Factory translation seams
without any infrastructure."""
import pytest

import service.store_service as store_service_mod
from models.domain.agent import AgentRole
from models.domain.openreview import OpenReviewNotes
from models.domain.paper import Author, Paper, PaperType
from models.domain.prompt import InstructionType, PromptInstruction, PromptVersion, SystemPromptPreset
from models.domain.retrieval import IndexInfo, RagFileSignature, RagIndex
from models.domain.run_record import AgentResponseRecord, GraphReviewRecord, GraphReviewSummary
from models.store.db import (
    AuthorTable,
    GraphReviewAgentTable,
    GraphReviewTable,
    PaperTable,
    PromptInstructionTable,
    PromptVersionTable,
    SystemPromptPresetTable,
)
from models.store.redis import AgentTraceRecord, RagIndex as StoreRagIndex
from domain.store.db.open_review_adapter import OpenReviewAdapter
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


def _neurips_review_note() -> dict:
    """NeurIPS-style note, API v2 shape: ``invitations`` list and every content
    field wrapped as {"value": ...}, with limitations and the sub-scores."""
    return {
        "id": "n2",
        "invitations": ["NeurIPS.cc/2023/Conference/Submission1/-/Official_Review"],
        "signatures": ["NeurIPS.cc/2023/Conference/Submission1/Reviewer_xyz"],
        "content": {
            "summary": {"value": "NS"},
            "strengths": {"value": "solid"},
            "weaknesses": {"value": "narrow"},
            "questions": {"value": "q?"},
            "limitations": {"value": "not discussed"},
            "soundness": {"value": "3 good"},
            "presentation": {"value": "2 fair"},
            "contribution": {"value": "3 good"},
            "rating": {"value": "7: Accept"},
            "confidence": {"value": "4: You are confident"},
        },
    }


def _meta_review_note() -> dict:
    return {
        "id": "n3", "invitation": "ICLR/-/Meta_Review", "signatures": ["ICLR/Area_Chair1"],
        "content": {"metareview": "Overall solid work.", "recommendation": "Accept"},
    }


def _decision_note() -> dict:
    return {
        "id": "n4", "invitation": "ICLR/-/Decision", "signatures": ["ICLR/Program_Chairs"],
        "content": {"decision": "Accept"},
    }


class FakeRuns:
    """Stand-in for DbRunRepository."""
    saved: dict = {}

    def __init__(self):
        pass

    def save_rows(self, run_row, agent_rows):
        FakeRuns.saved = {"run_row": run_row, "agent_rows": agent_rows}
        return "RID-123"

    def list_summaries(self):
        return [GraphReviewTable(run_id="R1", timestamp="t", paper_id="other_p_pdf", decision="accept", total_rounds=1)]

    def get_rows(self, run_id):
        if run_id == "missing":
            return None
        run_row = GraphReviewTable(run_id=run_id, timestamp="t", paper_id="other_p_pdf", decision="accept", total_rounds=2, graph_config={"max_rounds": 3})
        agent_row = GraphReviewAgentTable(id=1, run_id=run_id, agent_role="reviewer", agent_index=1, round=0, rating=6, trace_index=0, response_payload={"rating": 6})
        return (run_row, [agent_row])

    @staticmethod
    def build_run_id(paper_id):
        return "built:" + paper_id

    def list_run_ids_for_paper(self, paper_id):
        return ["R1", "R2"] if paper_id == "other_p_pdf" else []


class FakeAgentTraces:
    """Stand-in for RedisAgentTraceRepository."""
    saved: dict = {}

    def __init__(self):
        pass

    def save_traces(self, run_id, traces):
        FakeAgentTraces.saved = {"run_id": run_id, "traces": traces}

    def load_traces(self, run_id):
        if run_id == "no-bundle":
            return None
        return [AgentTraceRecord(input_message="m", context_used="ctx", response_payload={"rating": 6})]


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

    def list_ids(self):
        return ["other_p_pdf"]

    def list_openreview(self):
        return [PaperTable(id=3, paper_id="or_p_pdf", paper_name="OR", paper_type="OPEN_REVIEW")]


class FakePrompts:
    """Stand-in for DbPromptRepository."""

    def __init__(self):
        pass

    def list(self, agent_role=None, include_inactive=False):
        return [PromptVersionTable(id=1, agent_role=agent_role or "reviewer", version_label="v1", template="t", template_hash="h", created_at="t")]

    def get(self, version_id):
        return None if version_id == 999 else PromptVersionTable(id=version_id, agent_role="reviewer", version_label="v1", template="t", template_hash="h", created_at="t")

    def get_by_role_label(self, agent_role, version_label, only_active=True):
        return None if version_label == "missing" else PromptVersionTable(id=2, agent_role=agent_role, version_label=version_label, template="t", template_hash="h", created_at="t")

    def create(self, agent_role, version_label, template, description=None):
        return None if version_label == "dup" else PromptVersionTable(id=3, agent_role=agent_role, version_label=version_label, template=template, template_hash="h", created_at="t", description=description)

    def update_meta(self, version_id, description=None, is_active=None):
        if version_id == 999:
            return None
        return PromptVersionTable(id=version_id, agent_role="reviewer", version_label="v1", template="t", template_hash="h", created_at="t", description=description, is_active=is_active if is_active is not None else True)

    def seed_defaults(self, seeds) -> int:
        return 0


class FakeAuthors:
    """Stand-in for DbAuthorRepository."""
    linked: list = []

    def __init__(self):
        pass

    def get_or_create(self, row):
        row.id = 7
        return row

    def link_to_paper(self, paper_id, author_id, position):
        FakeAuthors.linked.append((paper_id, author_id, position))

    def list_for_paper(self, paper_id):
        return [(AuthorTable(id=7, full_name="Jane Doe", email="jane@example.com"), 1)]

    def list_papers_for_author(self, author_id):
        return ["other_p_pdf"] if author_id == 7 else []


class FakeInstructions:
    """Stand-in for DbInstructionRepository."""

    def __init__(self):
        pass

    def list_by_labels(self, labels):
        return [PromptInstructionTable(id=1, type="intention", label=labels[0] if labels else "l", instruction="i", created_at="t")]

    def list_by_ids(self, ids):
        return [PromptInstructionTable(id=ids[0], type="intention", label="l", instruction="i", created_at="t")] if ids else []

    def list(self, type=None, include_inactive=False):
        return [PromptInstructionTable(id=1, type=type or "intention", label="l", instruction="i", created_at="t")]

    def create(self, type, label, instruction, description=None, agent_role=None, run_id=None):
        if label == "dup":
            return None
        return PromptInstructionTable(id=2, type=type, label=label, instruction=instruction, description=description, agent_role=agent_role, run_id=run_id, created_at="t")

    def update_meta(self, instruction_id, description=None, is_active=None):
        if instruction_id == 999:
            return None
        return PromptInstructionTable(id=instruction_id, type="intention", label="l", instruction="i", created_at="t", description=description, is_active=is_active if is_active is not None else True)

    def seed_defaults(self, seeds) -> int:
        return 0


class FakePresets:
    """Stand-in for DbPresetRepository."""
    seeded: list = []

    def __init__(self):
        pass

    def list(self, agent_role=None, include_inactive=False):
        return [SystemPromptPresetTable(id=1, agent_role=agent_role or "reviewer", name="severo", base_prompt_version="v1", instruction_ids=[3, 7], created_at="t")]

    def get(self, preset_id):
        return None if preset_id == 999 else SystemPromptPresetTable(id=preset_id, agent_role="reviewer", name="severo", base_prompt_version="v1", instruction_ids=[3], created_at="t")

    def create(self, agent_role, name, base_prompt_version, instruction_ids=None, description=None):
        if name == "dup":
            return None
        return SystemPromptPresetTable(id=2, agent_role=agent_role, name=name, base_prompt_version=base_prompt_version, instruction_ids=list(instruction_ids or []), description=description, created_at="t")

    def update(self, preset_id, name=None, description=None, base_prompt_version=None, instruction_ids=None, is_active=None):
        if preset_id == 999 or name == "dup":
            return None
        return SystemPromptPresetTable(
            id=preset_id, agent_role="reviewer", name=name or "severo",
            base_prompt_version=base_prompt_version or "v1",
            instruction_ids=list(instruction_ids) if instruction_ids is not None else [3],
            description=description, created_at="t", updated_at="t2",
            is_active=is_active if is_active is not None else True,
        )

    def delete(self, preset_id):
        return preset_id != 999

    def seed_defaults(self, seeds):
        FakePresets.seeded = seeds
        return len(seeds)


class FakeRagIndex:
    """Stand-in for RedisRagIndexRepository."""
    saved = None

    def __init__(self):
        pass

    def load(self, doc_id):
        return None if doc_id == "missing" else _store_rag_index()

    def save(self, record):
        FakeRagIndex.saved = record

    def list_indexed(self):
        return ["d1", "d2"]

    @staticmethod
    def compute_doc_id(paper_id, strategy, strategy_version):
        return f"doc:{paper_id}:{strategy}:{strategy_version}"


class FakeOpenReviewDb:
    """Stand-in for DbOpenReviewRepository. ``list_by_paper`` serves rows built
    from the note fixtures through the REAL OpenReviewAdapter, so the read path
    (rows -> HumanReview/HumanMetaReview) is exercised end-to-end."""
    saved: list = []

    def __init__(self):
        pass

    def create_batch(self, records):
        FakeOpenReviewDb.saved.extend(records)

    def list_by_paper(self, paper_id):
        if paper_id == "missing":
            return []
        notes = OpenReviewNotes.from_notes([_review_note(), _neurips_review_note(), _meta_review_note(), _decision_note()])
        return OpenReviewAdapter.from_notes(notes, paper_id)


class FakeFiles:
    """Stand-in for FilePaperRepository."""
    saved: dict = {}

    def __init__(self):
        pass

    def resolve(self, paper_id):
        return f"/papers/{paper_id}"

    def signature(self, paper_id):
        return RagFileSignature(mtime_ns=123, size=456)

    def file_format(self, paper_id):
        return "pdf"

    def save(self, paper_id, data):
        FakeFiles.saved[paper_id] = data


@pytest.fixture
def service(monkeypatch) -> StoreService:
    monkeypatch.setattr(store_service_mod, "DbRunRepository", FakeRuns)
    monkeypatch.setattr(store_service_mod, "DbPaperRepository", FakePapers)
    monkeypatch.setattr(store_service_mod, "DbAuthorRepository", FakeAuthors)
    monkeypatch.setattr(store_service_mod, "DbPromptRepository", FakePrompts)
    monkeypatch.setattr(store_service_mod, "DbInstructionRepository", FakeInstructions)
    monkeypatch.setattr(store_service_mod, "DbPresetRepository", FakePresets)
    monkeypatch.setattr(store_service_mod, "RedisRagIndexRepository", FakeRagIndex)
    monkeypatch.setattr(store_service_mod, "RedisAgentTraceRepository", FakeAgentTraces)
    monkeypatch.setattr(store_service_mod, "DbOpenReviewRepository", FakeOpenReviewDb)
    monkeypatch.setattr(store_service_mod, "FilePaperRepository", FakeFiles)
    return StoreService()


def _run_record() -> GraphReviewRecord:
    return GraphReviewRecord(
        run_id="RID", timestamp="t", paper_id="other_p_pdf", decision="accept", total_rounds=2,
        reviews_response=[{"summary": "r"}], meta_review_response={"overall_score": 7}, author_response=None,
        graph_config={"max_rounds": 3},
        agent_records=[AgentResponseRecord(agent_role=AgentRole.REVIEWER, agent_index=1, round=0, input_message="m", context_used=None, response_payload={"rating": 6})],
    )


class TestRuns:
    def test_save_run_applies_factory_and_returns_id(self, service):
        assert service.save_run(_run_record()) == "RID-123"
        run_row = FakeRuns.saved["run_row"]
        assert isinstance(run_row, GraphReviewTable)
        assert run_row.max_rounds == 3 and run_row.meta_overall_score == 7  # Factory extracted these
        assert run_row.graph_config == {"max_rounds": 3}
        assert len(FakeRuns.saved["agent_rows"]) == 1
        agent_row = FakeRuns.saved["agent_rows"][0]
        assert isinstance(agent_row, GraphReviewAgentTable)
        assert agent_row.trace_index == 0
        # the verbatim trace went to the Redis bundle, under the saved run_id
        assert FakeAgentTraces.saved["run_id"] == "RID-123"
        traces = FakeAgentTraces.saved["traces"]
        assert len(traces) == 1 and isinstance(traces[0], AgentTraceRecord)
        assert traces[0].input_message == "m"

    def test_list_runs_maps_rows_to_summaries(self, service):
        summaries = service.list_runs()
        assert len(summaries) == 1 and isinstance(summaries[0], GraphReviewSummary)
        assert summaries[0].run_id == "R1"

    def test_get_run_returns_none_when_missing(self, service):
        assert service.get_run("missing") is None

    def test_get_run_builds_full_record_via_adapter(self, service):
        record = service.get_run("R1")
        assert isinstance(record, GraphReviewRecord)
        assert record.reviews_response == [{"rating": 6}]  # derived from the reviewer row
        assert record.graph_config == {"max_rounds": 3}
        assert record.agent_records[0].agent_role is AgentRole.REVIEWER and record.agent_records[0].agent_index == 1
        assert record.agent_records[0].response_payload == {"rating": 6}
        assert record.agent_records[0].input_message == "m"  # from the Redis trace
        assert record.agent_records[0].context_used == "ctx"

    def test_get_run_degrades_without_trace_bundle(self, service):
        record = service.get_run("no-bundle")
        assert record.reviews_response == [{"rating": 6}]  # facts rows still serve the payload
        assert record.agent_records[0].input_message is None  # verbatim fields gone with the bundle

    def test_build_run_id_delegates_to_repository(self, service):
        assert service.build_run_id("other_p_pdf") == "built:other_p_pdf"

    def test_get_run_ids_for_paper_delegates_to_repository(self, service):
        assert service.get_run_ids_for_paper("other_p_pdf") == ["R1", "R2"]
        assert service.get_run_ids_for_paper("unknown") == []


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
        result = service.create_paper(Paper(paper_id="ignored", paper_name="My Paper", paper_type=PaperType.OTHER), "pdf")
        assert isinstance(result, Paper)
        assert result.id == 99
        assert result.paper_id.endswith("_pdf")  # generated uid + format suffix
        assert result.paper_name == "My Paper"  # user-typed name, untouched
        assert FakePapers.created.paper_type == "OTHER"  # Factory unwrapped the enum

    def test_list_paper_ids_delegates_to_repository(self, service):
        assert service.list_paper_ids() == ["other_p_pdf"]

    def test_list_openreview_papers_maps_to_domain(self, service):
        papers = service.list_openreview_papers()
        assert len(papers) == 1 and papers[0].paper_type is PaperType.OPEN_REVIEW

    def test_save_paper_creates_file_and_links_authors(self, service):
        paper = Paper(paper_id="ignored", paper_name="My Paper", paper_type=PaperType.OTHER)
        authors = [Author(full_name="Jane Doe", email="jane@example.com")]
        result = service.save_paper(paper, b"data", "pdf", authors)
        assert isinstance(result, Paper)
        assert result.paper_id in FakeFiles.saved and FakeFiles.saved[result.paper_id] == b"data"
        assert FakeAuthors.linked[-1][0] == result.paper_id

    def test_save_paper_returns_none_when_paper_id_exists(self, service, monkeypatch):
        monkeypatch.setattr(FakePapers, "create", lambda self, row: None)
        paper = Paper(paper_id="ignored", paper_name="My Paper", paper_type=PaperType.OTHER)
        assert service.save_paper(paper, b"data", "pdf") is None


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

    def test_list_indexed_papers_delegates_to_repository(self, service):
        assert service.list_indexed_papers() == ["d1", "d2"]


class TestOpenReview:
    def test_get_human_reviews_parses_rows_end_to_end(self, service):
        reviews = service.get_human_reviews("k")
        assert len(reviews) == 2
        assert reviews[0].reviewer_id == "Reviewer_abc"
        assert reviews[0].summary == "S"
        assert (reviews[0].rating, reviews[0].confidence) == (6, 4)

    def test_get_human_reviews_parses_neurips_v2_note(self, service):
        review = service.get_human_reviews("k")[1]
        assert review.reviewer_id == "Reviewer_xyz"
        assert (review.summary, review.strengths) == ("NS", "solid")
        assert (review.rating, review.confidence) == (7, 4)
        assert (review.soundness, review.presentation, review.contribution) == (3, 2, 3)

    def test_get_human_reviews_empty_when_paper_missing(self, service):
        assert service.get_human_reviews("missing") == []

    def test_save_open_review_data_persists_parsed_rows(self, service):
        FakeOpenReviewDb.saved = []
        service.save_open_review_data("p1", OpenReviewNotes.from_notes([_review_note(), _decision_note()]))
        assert len(FakeOpenReviewDb.saved) == 2
        assert {row.reviewer_type for row in FakeOpenReviewDb.saved} == {"reviewer", "area_chair"}
        assert all(row.paper_id == "p1" for row in FakeOpenReviewDb.saved)

    def test_get_open_review_data_includes_area_chair_decision(self, service):
        rows = service.get_open_review_data("k")
        decision_rows = [row for row in rows if row.reviewer_type == "area_chair"]
        assert len(decision_rows) == 1 and decision_rows[0].decision == "Accept"

    def test_get_human_meta_review_parses_rows(self, service):
        meta_review = service.get_human_meta_review("k")
        assert meta_review.text == "Overall solid work."
        assert meta_review.recommendation == "Accept"

    def test_get_human_meta_review_none_when_paper_missing(self, service):
        assert service.get_human_meta_review("missing") is None


class TestAuthors:
    def test_save_paper_authors_links_and_returns_domain_authors(self, service):
        authors = [Author(full_name="Jane Doe", email="jane@example.com")]
        linked = service.save_paper_authors("other_p_pdf", authors)
        assert len(linked) == 1 and isinstance(linked[0], Author)
        assert linked[0].id == 7 and linked[0].position == 1
        assert FakeAuthors.linked[-1] == ("other_p_pdf", 7, 1)

    def test_get_paper_authors_maps_pairs_to_domain(self, service):
        authors = service.get_paper_authors("other_p_pdf")
        assert len(authors) == 1 and isinstance(authors[0], Author)
        assert authors[0].full_name == "Jane Doe" and authors[0].position == 1

    def test_get_papers_for_author_delegates_to_repository(self, service):
        assert service.get_papers_for_author(7) == ["other_p_pdf"]
        assert service.get_papers_for_author(1) == []


class TestPrompts:
    def test_list_prompts_maps_rows_to_domain(self, service):
        prompts = service.list_prompts("reviewer")
        assert len(prompts) == 1 and isinstance(prompts[0], PromptVersion)
        assert prompts[0].agent_role == "reviewer"

    def test_get_prompt_returns_none_when_missing(self, service):
        assert service.get_prompt(999) is None

    def test_get_prompt_maps_row(self, service):
        prompt = service.get_prompt(5)
        assert isinstance(prompt, PromptVersion) and prompt.id == 5

    def test_get_promt_by_role_label_returns_none_when_missing(self, service):
        assert service.get_promt_by_role_label("reviewer", "missing") is None

    def test_get_promt_by_role_label_maps_row(self, service):
        prompt = service.get_promt_by_role_label("reviewer", "v2")
        assert isinstance(prompt, PromptVersion) and prompt.version_label == "v2"

    def test_create_prompt_returns_none_on_duplicate(self, service):
        assert service.create_prompt("reviewer", "dup", "template") is None

    def test_create_prompt_maps_row(self, service):
        prompt = service.create_prompt("reviewer", "v3", "template", "desc")
        assert isinstance(prompt, PromptVersion) and prompt.template == "template"

    def test_update_prompt_meta_returns_none_when_missing(self, service):
        assert service.update_prompt_meta(999) is None

    def test_update_prompt_meta_maps_row(self, service):
        prompt = service.update_prompt_meta(5, description="new desc", is_active=False)
        assert isinstance(prompt, PromptVersion) and prompt.description == "new desc" and prompt.is_active is False


class TestInstructions:
    def test_get_instructions_by_labels_maps_rows(self, service):
        instructions = service.get_instructions_by_labels(["confident"])
        assert len(instructions) == 1 and isinstance(instructions[0], PromptInstruction)
        assert instructions[0].label == "confident"

    def test_list_instructions_maps_rows(self, service):
        instructions = service.list_instructions(InstructionType.INTENTION)
        assert len(instructions) == 1 and instructions[0].type is InstructionType.INTENTION

    def test_create_instruction_returns_none_on_duplicate(self, service):
        assert service.create_instruction(InstructionType.FOCUS, "dup", "text") is None

    def test_create_instruction_maps_row(self, service):
        instruction = service.create_instruction(InstructionType.FOCUS, "narrow", "text", "desc", "reviewer")
        assert isinstance(instruction, PromptInstruction) and instruction.label == "narrow"

    def test_update_instruction_meta_returns_none_when_missing(self, service):
        assert service.update_instruction_meta(999) is None

    def test_update_instruction_meta_maps_row(self, service):
        instruction = service.update_instruction_meta(1, description="new desc", is_active=False)
        assert isinstance(instruction, PromptInstruction) and instruction.description == "new desc" and instruction.is_active is False

    def test_get_instructions_by_ids_maps_rows(self, service):
        instructions = service.get_instructions_by_ids([7])
        assert len(instructions) == 1 and isinstance(instructions[0], PromptInstruction)
        assert instructions[0].id == 7


class TestPresets:
    def test_list_presets_maps_rows_to_domain(self, service):
        presets = service.list_presets("reviewer")
        assert len(presets) == 1 and isinstance(presets[0], SystemPromptPreset)
        assert presets[0].name == "severo" and presets[0].instruction_ids == [3, 7]

    def test_get_preset_returns_none_when_missing(self, service):
        assert service.get_preset(999) is None

    def test_get_preset_maps_row(self, service):
        preset = service.get_preset(1)
        assert isinstance(preset, SystemPromptPreset) and preset.base_prompt_version == "v1"

    def test_create_preset_returns_none_on_duplicate(self, service):
        assert service.create_preset("reviewer", "dup", "v1") is None

    def test_create_preset_maps_row(self, service):
        preset = service.create_preset("reviewer", "empirico", "v1", [3, 7], "desc")
        assert isinstance(preset, SystemPromptPreset)
        assert preset.name == "empirico" and preset.instruction_ids == [3, 7] and preset.description == "desc"

    def test_update_preset_returns_none_when_missing(self, service):
        assert service.update_preset(999, name="x") is None

    def test_update_preset_maps_row(self, service):
        preset = service.update_preset(1, name="nuovo", instruction_ids=[9], is_active=False)
        assert isinstance(preset, SystemPromptPreset)
        assert preset.name == "nuovo" and preset.instruction_ids == [9] and preset.is_active is False

    def test_delete_preset_delegates_to_repository(self, service):
        assert service.delete_preset(1) is True
        assert service.delete_preset(999) is False

    def test_seed_presets_resolves_instruction_refs_to_ids(self, service):
        seeds = [(
            "reviewer", "default", "base_v1",
            [(InstructionType.INTENTION, "l"), (InstructionType.FOCUS, "missing")],
            "desc",
        )]
        assert service.seed_presets(seeds) == 1
        agent_role, name, base_version, instruction_ids, description = FakePresets.seeded[0]
        assert (agent_role, name, base_version, description) == ("reviewer", "default", "base_v1", "desc")
        assert instruction_ids == [1]  # (intention, l) resolved; unknown ref dropped


class TestFiles:
    def test_get_source_path_for_paper_delegates_to_repository(self, service):
        assert service.get_source_path_for_paper("other_p_pdf") == "/papers/other_p_pdf"

    def test_signature_delegates_to_repository(self, service):
        signature = service.signature("other_p_pdf")
        assert isinstance(signature, RagFileSignature) and signature.mtime_ns == 123

    def test_file_format_delegates_to_repository(self, service):
        assert service.file_format("other_p_pdf") == "pdf"

    def test_save_paper_file_delegates_to_repository(self, service):
        service.save_paper_file("other_p_pdf", b"raw bytes")
        assert FakeFiles.saved["other_p_pdf"] == b"raw bytes"
