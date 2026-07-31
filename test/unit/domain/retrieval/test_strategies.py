"""Unit tests for the retrieval strategies (domain/retrieval/base.py): the
pluggable RetrievalStrategy (full_context / bm25 / embedding), the Chunker, the
MockEmbedder and the factory. No real embedding model or DB involved."""
import pytest

from models.domain.retrieval import RagFileSignature, RagSectionEntry, RagStrategy
from domain.retrieval.base import (
    Bm25Strategy,
    Chunker,
    EmbeddingStrategy,
    FullContextStrategy,
    MockEmbedder,
    RetrievalStrategy,
)


def _sig() -> RagFileSignature:
    return RagFileSignature(mtime_ns=1, size=2)


# Three short sections, each fits in one chunk, with disjoint keywords.
_RAW = [
    ("Methods", "we optimize the model with stochastic gradient descent"),
    ("Results", "accuracy improved substantially on the imagenet benchmark"),
    ("Related Work", "prior transformers explored attention mechanisms"),
]


class TestFullContext:
    def test_build_context_concatenates_all_sections(self):
        strategy = FullContextStrategy("v1")
        index = strategy.build_index(_RAW, "p.txt", "d", _sig())
        context = strategy.build_context(index, "query is ignored")
        assert "# Methods" in context and "# Results" in context and "# Related Work" in context
        assert "imagenet" in context and "gradient" in context  # whole paper present


class TestBm25:
    def test_build_index_produces_chunks(self):
        index = Bm25Strategy("v1", Chunker()).build_index(_RAW, "p.txt", "d", _sig())
        assert index.settings.strategy is RagStrategy.BM25
        assert index.sections == []
        assert len(index.chunks) == 3
        assert index.chunks[0].section == "Methods"

    def test_build_context_ranks_relevant_chunk_first(self):
        strategy = Bm25Strategy("v1", Chunker(), top_k=1)
        index = strategy.build_index(_RAW, "p.txt", "d", _sig())
        context = strategy.build_context(index, "imagenet accuracy benchmark")
        assert "imagenet" in context and "accuracy" in context
        assert "gradient" not in context  # only the top-1 (Results) chunk


class TestEmbedding:
    def test_build_index_sets_embeddings(self):
        index = EmbeddingStrategy("v1", Chunker(), MockEmbedder()).build_index(_RAW, "p.txt", "d", _sig())
        assert index.settings.strategy is RagStrategy.EMBEDDING
        assert len(index.chunks) == 3
        assert all(chunk.embedding is not None for chunk in index.chunks)

    def test_build_context_ranks_by_similarity(self):
        strategy = EmbeddingStrategy("v1", Chunker(), MockEmbedder(), top_k=1)
        index = strategy.build_index(_RAW, "p.txt", "d", _sig())
        context = strategy.build_context(index, "imagenet accuracy benchmark")
        assert "imagenet" in context
        assert "gradient" not in context


class TestFactory:
    def test_create_returns_the_right_strategy(self):
        assert isinstance(RetrievalStrategy.create(RagStrategy.FULL_CONTEXT, "v1"), FullContextStrategy)
        assert isinstance(RetrievalStrategy.create(RagStrategy.BM25, "v1"), Bm25Strategy)
        assert isinstance(RetrievalStrategy.create(RagStrategy.EMBEDDING, "v1", embedder=MockEmbedder()), EmbeddingStrategy)

    def test_create_embedding_requires_an_embedder(self):
        with pytest.raises(ValueError):
            RetrievalStrategy.create(RagStrategy.EMBEDDING, "v1")


class TestMockEmbedder:
    def test_is_deterministic_and_normalized(self):
        embedder = MockEmbedder()
        [first] = embedder.embed(["hello world"])
        [second] = embedder.embed(["hello world"])
        assert first == second
        assert abs(sum(value * value for value in first) ** 0.5 - 1.0) < 1e-9


class TestChunker:
    def test_splits_with_overlap_and_tags_section(self):
        chunks = Chunker(chunk_size=10, overlap=4).chunk([RagSectionEntry(name="S", text="0123456789ABCDEFGHIJ")])
        assert all(chunk.section == "S" for chunk in chunks)
        assert chunks[0].text == "0123456789"
        assert chunks[1].text.startswith("6789")  # step = chunk_size - overlap = 6
