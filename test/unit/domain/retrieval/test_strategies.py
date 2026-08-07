"""Unit tests for the retrieval strategies (domain/retrieval/base.py): the
pluggable RetrievalStrategy (full_context / bm25 / embedding / summary), the
Chunker, the MockEmbedder and the factory. No real LLM, embedding model or DB
involved."""
import pytest

from models.domain.retrieval import RagFileSignature, RagSectionEntry, RagStrategy, RagTokenUsage, SummaryResult
from domain.retrieval.base import (
    Bm25Strategy,
    Chunker,
    EmbeddingStrategy,
    FullContextStrategy,
    MockEmbedder,
    RetrievalStrategy,
    Summarizer,
    SummaryStrategy,
)


class FakeSummarizer(Summarizer):
    """Records the sections it received and returns a fixed summary."""

    def __init__(self):
        self.calls: list[list[RagSectionEntry]] = []

    def summarize(self, sections: list[RagSectionEntry]) -> SummaryResult:
        self.calls.append(sections)
        return SummaryResult(
            summary="a faithful short summary",
            token_usage=RagTokenUsage(input_tokens=100, output_tokens=20, total_tokens=120),
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

    def test_matching_is_punctuation_and_case_insensitive(self):
        # Three docs so BM25 IDF stays positive; punctuation glued to the terms.
        raw = [
            ("Methods", "We optimize with gradient descent."),
            ("Results", "Accuracy improved, substantially, on ImageNet!"),
            ("Related Work", "Prior transformers explored attention mechanisms."),
        ]
        strategy = Bm25Strategy("v2", Chunker(), top_k=1)
        index = strategy.build_index(raw, "p.txt", "d", _sig())
        # "imagenet" (bare, lowercased) must match "ImageNet!" in the text.
        context = strategy.build_context(index, "imagenet accuracy")
        assert "ImageNet" in context
        assert "gradient" not in context


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


class TestSummary:
    def test_build_index_stores_one_summary_section(self):
        summarizer = FakeSummarizer()
        index = SummaryStrategy("v1-mock", summarizer).build_index(_RAW, "p.txt", "d", _sig())
        assert index.settings.strategy is RagStrategy.SUMMARY
        assert index.chunks == []
        assert [section.name for section in index.sections] == ["summary"]
        assert index.sections[0].text == "a faithful short summary"
        assert index.token_usage is not None and index.token_usage.total_tokens == 120
        assert len(summarizer.calls) == 1  # LLM cost paid at index time only
        assert [section.name for section in summarizer.calls[0]] == ["Methods", "Results", "Related Work"]

    def test_build_context_ignores_the_query(self):
        strategy = SummaryStrategy("v1-mock", FakeSummarizer())
        index = strategy.build_index(_RAW, "p.txt", "d", _sig())
        assert strategy.build_context(index, "any query") == "a faithful short summary"
        assert strategy.build_context(index, "") == "a faithful short summary"


class TestFactory:
    def test_create_returns_the_right_strategy(self):
        assert isinstance(RetrievalStrategy.create(RagStrategy.FULL_CONTEXT, "v1"), FullContextStrategy)
        assert isinstance(RetrievalStrategy.create(RagStrategy.BM25, "v1"), Bm25Strategy)
        assert isinstance(RetrievalStrategy.create(RagStrategy.EMBEDDING, "v1", embedder=MockEmbedder()), EmbeddingStrategy)
        assert isinstance(RetrievalStrategy.create(RagStrategy.SUMMARY, "v1", summarizer=FakeSummarizer()), SummaryStrategy)

    def test_create_embedding_requires_an_embedder(self):
        with pytest.raises(ValueError):
            RetrievalStrategy.create(RagStrategy.EMBEDDING, "v1")

    def test_create_summary_requires_a_summarizer(self):
        with pytest.raises(ValueError):
            RetrievalStrategy.create(RagStrategy.SUMMARY, "v1")


class TestMockEmbedder:
    def test_is_deterministic_and_normalized(self):
        embedder = MockEmbedder()
        [first] = embedder.embed(["hello world"])
        [second] = embedder.embed(["hello world"])
        assert first == second
        assert abs(sum(value * value for value in first) ** 0.5 - 1.0) < 1e-9


class TestChunker:
    def test_packs_whole_sentences_up_to_the_budget(self):
        text = "One two three. Four five six. Seven eight nine."
        chunks = Chunker(chunk_size=32, overlap=0).chunk([RagSectionEntry(name="S", text=text)])
        assert all(chunk.section == "S" for chunk in chunks)
        assert chunks[0].text == "One two three. Four five six."  # two sentences fit
        assert chunks[1].text == "Seven eight nine."

    def test_never_cuts_mid_word(self):
        text = "alpha beta gamma delta epsilon zeta eta theta iota kappa " * 20
        words = set(text.split())
        chunks = Chunker(chunk_size=100, overlap=20).chunk([RagSectionEntry(name="S", text=text)])
        assert len(chunks) > 1
        for chunk in chunks:
            assert set(chunk.text.split()) <= words  # every token is a whole word

    def test_overlap_seeds_the_next_chunk_with_the_previous_tail(self):
        text = "First sentence here. Second sentence here. Third sentence here."
        chunks = Chunker(chunk_size=45, overlap=25).chunk([RagSectionEntry(name="S", text=text)])
        assert len(chunks) >= 2
        # The second chunk starts with the trailing sentence of the first.
        last_sentence_of_first = chunks[0].text.split(". ")[-1].rstrip(".")
        assert chunks[1].text.startswith(last_sentence_of_first.split()[0])

    def test_oversized_sentence_falls_back_to_word_packing(self):
        text = "word " * 50  # one 250-char "sentence" with no terminator
        chunks = Chunker(chunk_size=60, overlap=0).chunk([RagSectionEntry(name="S", text=text)])
        assert len(chunks) > 1
        assert all(len(chunk.text) <= 60 for chunk in chunks)
        assert all(piece == "word" for chunk in chunks for piece in chunk.text.split())
