"""Primary store for the agent traces (keyspace agent-trace), one
AgentTraceBundle per run. The context text handed to an agent is deduplicated
into the agent-context keyspace: one blob per SHA-256 of the text (SETNX, so
an existing blob is never rewritten), shared across traces and runs — a
committee of N reviewers reading the same paper stores the context once, not
N times. Context blobs are content-addressed and shared, so deleting a run's
bundle never removes them.
"""
from hashlib import sha256

from domain.store.redis.repository import AGENT_CONTEXT_KEYSPACE, AGENT_TRACE_KEYSPACE, RedisRepository
from models.store.redis import AgentTraceBundle, AgentTraceRecord


class RedisAgentTraceRepository(RedisRepository):
    """Agent trace store backed by Redis. ttl_seconds <= 0 = permanent store."""

    def __init__(self, ttl_seconds: int = 0):
        super().__init__(AGENT_TRACE_KEYSPACE, ttl_seconds)

    @staticmethod
    def compute_context_hash(text: str) -> str:
        return sha256(text.encode("utf-8")).hexdigest()

    def save_traces(self, run_id: str, traces: list[AgentTraceRecord]) -> None:
        """Persist the run's traces as one bundle, in invocation order.
        Saving an existing run_id replaces its bundle. Each context text is
        swapped for its hash and written once to the agent-context keyspace."""
        stored: list[AgentTraceRecord] = []
        for trace in traces:
            record = trace.model_copy()
            if record.context_used is not None:
                record.context_hash = self._store_context(record.context_used)
                record.context_used = None
            stored.append(record)
        bundle = AgentTraceBundle(run_id=run_id, traces=stored)
        self._set(run_id, bundle.model_dump_json())

    def load_traces(self, run_id: str) -> list[AgentTraceRecord] | None:
        """The run's traces in invocation order, with the context texts
        resolved back from their hashes. None when the run has no bundle."""
        bundle = self._load(run_id, AgentTraceBundle, label="agent trace bundle")
        if bundle is None:
            return None
        for record in bundle.traces:
            if record.context_hash is not None:
                record.context_used = self._client.get(AGENT_CONTEXT_KEYSPACE.key(record.context_hash))
        return bundle.traces

    def delete_traces(self, run_id: str) -> None:
        """Remove the run's bundle. The context blobs stay: they are
        content-addressed and shared with other runs."""
        self._delete(run_id)

    def _store_context(self, text: str) -> str:
        """Write the context blob under its content hash — SETNX, so identical
        contexts are stored exactly once. Returns the hash."""
        context_hash = self.compute_context_hash(text)
        self._client.setnx(AGENT_CONTEXT_KEYSPACE.key(context_hash), text)
        return context_hash
