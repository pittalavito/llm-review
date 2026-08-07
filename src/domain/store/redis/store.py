"""Redis store facade: one import point for the Redis persistence layer.

Re-exports the Redis repositories and holds the Redis translation seams as
static-method classes. ``Adapter`` (reads) parses the stored records into domain
models: ``RagIndex`` -> ``IndexInfo`` + full paper text. ``Factory`` (writes)
builds the stored records: ``AgentResponseRecord`` -> ``AgentTraceRecord``.
"""
from domain.store.redis.agent_trace_repository import RedisAgentTraceRepository
from domain.store.redis.rag_index_repository import RedisRagIndexRepository
from models.store.redis import AgentTraceRecord, RagIndex as StoreRagIndex

from models.domain.retrieval import IndexInfo, RagIndex
from models.domain.run_record import AgentResponseRecord

__all__ = ["RedisAgentTraceRepository", "RedisRagIndexRepository", "Adapter", "Factory"]


class Adapter:
    """Read seam: Redis records -> domain models (RAG index)."""

    @staticmethod
    def to_rag_index(record: StoreRagIndex) -> RagIndex:
        """Store ``RagIndex`` record -> domain ``RagIndex`` (deserialization only —
        same shape)."""
        return RagIndex.model_validate(record.model_dump())

    @staticmethod
    def to_index_info(index: RagIndex) -> IndexInfo:
        """``RagIndex`` record -> lightweight ``IndexInfo`` (metadata only)."""
        return IndexInfo(
            doc_id=index.doc_id,
            paper_id=index.paper_id,
            section_count=len(index.sections),
            token_usage=index.token_usage,
        )

    @staticmethod
    def to_full_paper_text(index: RagIndex) -> str:
        """Reassemble the whole paper from the index sections, in order, each with
        its heading — the full-context text handed to every agent."""
        return "\n\n".join(f"# {section.name}\n{section.text}" for section in index.sections)


class Factory:
    """Write seam: domain models -> Redis records."""

    @staticmethod
    def to_rag_index_record(index: RagIndex) -> StoreRagIndex:
        """Domain ``RagIndex`` -> store ``RagIndex`` record."""
        return StoreRagIndex.model_validate(index.model_dump())

    @staticmethod
    def to_agent_trace_record(agent_record: AgentResponseRecord) -> AgentTraceRecord:
        """``AgentResponseRecord`` -> the verbatim trace record. The context
        text travels in ``context_used``; the repository swaps it for its hash
        at save time."""
        return AgentTraceRecord(
            input_message=agent_record.input_message,
            system_prompt=agent_record.system_prompt,
            context_used=agent_record.context_used,
            response_payload=agent_record.response_payload,
            input_tokens=agent_record.input_tokens,
            output_tokens=agent_record.output_tokens,
            total_tokens=agent_record.total_tokens,
            latency_seconds=agent_record.latency_seconds,
        )

    @staticmethod
    def to_agent_trace_records(agent_records: list[AgentResponseRecord]) -> list[AgentTraceRecord]:
        return [Factory.to_agent_trace_record(record) for record in agent_records]
