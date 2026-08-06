"""Unit tests for the Redis store seams (domain/store/redis/store.py): the
RagIndex deserialization, doc-id computation, the full-paper-text join and the
agent-trace record building + context hashing. The OpenReview note parsing
moved to the SQL side — see
test/unit/domain/store/db/test_open_review_adapter.py. No Redis involved."""
from models.domain.agent import AgentRole
from models.domain.retrieval import IndexInfo, RagIndex
from models.domain.run_record import AgentResponseRecord
from models.store.redis import AgentTraceRecord, RagIndex as StoreRagIndex
from domain.store.redis.agent_trace_repository import RedisAgentTraceRepository
from domain.store.redis.rag_index_repository import RedisRagIndexRepository
from domain.store.redis.store import Adapter, Factory


class TestComputeDocId:
    def test_composite_readable_id(self):
        doc_id = RedisRagIndexRepository.compute_doc_id("other_attention_pdf", "bm25", "v1")
        # <paper_id>+<strategy>-<version>
        assert doc_id == "other_attention_pdf+bm25-v1"

    def test_strategies_and_versions_get_distinct_ids(self):
        paper_id = "other_attention_pdf"
        ids = {
            RedisRagIndexRepository.compute_doc_id(paper_id, "full_context", "v1"),
            RedisRagIndexRepository.compute_doc_id(paper_id, "bm25", "v1"),
            RedisRagIndexRepository.compute_doc_id(paper_id, "bm25", "v2"),
        }
        assert len(ids) == 3  # coexist: no id collision -> no overwrite

    def test_unsafe_chars_in_strategy_are_slugged(self):
        doc_id = RedisRagIndexRepository.compute_doc_id("other_a_pdf", "bm 25", "v:1")
        assert ":" not in doc_id and " " not in doc_id


class Utils:
    """Static builders for store records."""

    @staticmethod
    def store_rag_index() -> StoreRagIndex:
        return StoreRagIndex.model_validate({
            "doc_id": "d1", "paper_id": "other_p_pdf",
            "file_signature": {"mtime_ns": 1, "size": 2},
            "settings": {"strategy_version": "v1"},
            "sections": [{"name": "Intro", "text": "hello"}, {"name": "Methods", "text": "world"}],
        })

    @staticmethod
    def rag_index() -> RagIndex:
        return Adapter.to_rag_index(Utils.store_rag_index())


class TestRagIndexAdapter:
    def test_to_rag_index_deserializes_same_shape(self):
        index = Adapter.to_rag_index(Utils.store_rag_index())
        assert isinstance(index, RagIndex)
        assert index.doc_id == "d1"
        assert [s.name for s in index.sections] == ["Intro", "Methods"]

    def test_to_index_info_counts_sections(self):
        info = Adapter.to_index_info(Utils.rag_index())
        assert isinstance(info, IndexInfo)
        assert (info.doc_id, info.paper_id, info.section_count) == ("d1", "other_p_pdf", 2)

    def test_to_full_paper_text_joins_sections_with_headings(self):
        assert Adapter.to_full_paper_text(Utils.rag_index()) == "# Intro\nhello\n\n# Methods\nworld"


class TestFactory:
    def test_to_rag_index_record_roundtrips(self):
        record = Factory.to_rag_index_record(Utils.rag_index())
        assert isinstance(record, StoreRagIndex)
        assert record.doc_id == "d1"
        assert len(record.sections) == 2

    def test_to_agent_trace_record_keeps_the_verbatim_fields(self):
        agent_record = AgentResponseRecord(
            agent_role=AgentRole.REVIEWER, agent_index=1, round=0,
            input_message="m", context_used="ctx", system_prompt="sp",
            response_payload={"rating": 6},
            input_tokens=100, output_tokens=50, total_tokens=150,
        )
        trace = Factory.to_agent_trace_record(agent_record)
        assert isinstance(trace, AgentTraceRecord)
        assert (trace.input_message, trace.context_used, trace.system_prompt) == ("m", "ctx", "sp")
        assert trace.context_hash is None  # the repository hashes at save time
        assert trace.response_payload == {"rating": 6}
        assert (trace.input_tokens, trace.output_tokens, trace.total_tokens) == (100, 50, 150)


class TestContextHash:
    def test_same_text_same_hash(self):
        assert (RedisAgentTraceRepository.compute_context_hash("full paper text")
                == RedisAgentTraceRepository.compute_context_hash("full paper text"))

    def test_different_text_different_hash(self):
        assert (RedisAgentTraceRepository.compute_context_hash("paper A")
                != RedisAgentTraceRepository.compute_context_hash("paper B"))
