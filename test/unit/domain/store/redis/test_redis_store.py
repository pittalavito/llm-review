"""Unit tests for the Redis store seams (domain/store/redis/store.py): the
RagIndex/OpenReview deserialization and, above all, the OpenReview note parser
(v1 flat content + v2 {"value": ...} wrapping) that produces the structured
HumanReview / HumanMetaReview / decision. No Redis involved."""
from domain.models.comparator import HumanMetaReview, HumanReview
from domain.models.openreview import OpenReviewCache
from domain.models.retrieval import IndexInfo, RagIndex
from domain.store.redis.models import OpenReviewCache as StoreOpenReviewCache, RagIndex as StoreRagIndex
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
    """Static builders for store records / note fixtures."""

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

    @staticmethod
    def review_note_v1() -> dict:
        return {
            "id": "n1", "invitation": "ICLR.cc/2024/-/Official_Review",
            "signatures": ["ICLR.cc/2024/Reviewer_abc"],
            "content": {
                "summary_of_the_paper": "S", "strength_and_weaknesses": "SW", "weaknesses": "W",
                "main_review": "MR", "rating": "6: marginally above the acceptance threshold",
                "confidence": "4: confident", "summary_of_the_review": "Q",
            },
        }

    @staticmethod
    def review_note_v2() -> dict:
        return {
            "id": "n2", "invitations": ["ICLR.cc/2024/-/Official_Review"],
            "signatures": ["ICLR.cc/2024/Reviewer_xyz"],
            "content": {
                "summary": {"value": "S2"}, "review": {"value": "R2"},
                "rating": {"value": "8: top 50%"}, "confidence": {"value": "5"},
            },
        }


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


class TestParserHelpers:
    def test_extract_int_leading_number(self):
        assert Adapter.extract_int("6: marginally above") == 6
        assert Adapter.extract_int("5") == 5
        assert Adapter.extract_int(7) == 7

    def test_extract_int_none_and_no_digits(self):
        assert Adapter.extract_int(None) is None
        assert Adapter.extract_int("no digits here") is None

    def test_unwrap_flattens_only_value_dicts(self):
        assert Adapter.unwrap({"a": {"value": 1}, "b": 2, "c": {"nested": 3}}) == {"a": 1, "b": 2, "c": {"nested": 3}}

    def test_invitation_text_handles_v1_str_and_v2_list(self):
        assert Adapter.invitation_text({"invitation": "X/Official_Review"}) == "x/official_review"
        assert Adapter.invitation_text({"invitations": ["A", "B"]}) == "a b"
        assert Adapter.invitation_text({}) == ""

    def test_get_returns_first_nonempty_and_coerces_to_str(self):
        assert Adapter.get({"a": "", "b": "x"}, "a", "b") == "x"
        assert Adapter.get({"n": 5}, "n") == "5"
        assert Adapter.get({}, "missing") is None


class TestHumanReviews:
    def test_parses_v1_flat_note(self):
        cache = OpenReviewCache.from_notes([Utils.review_note_v1()])
        reviews = Adapter.to_human_reviews(cache)
        assert len(reviews) == 1
        r = reviews[0]
        assert isinstance(r, HumanReview)
        assert r.reviewer_id == "Reviewer_abc"  # last signature segment
        assert (r.summary, r.strengths, r.weaknesses, r.full_text, r.questions) == ("S", "SW", "W", "MR", "Q")
        assert r.rating == 6 and r.rating_label.startswith("6:")
        assert r.confidence == 4

    def test_parses_v2_value_wrapped_note(self):
        cache = OpenReviewCache.from_notes([Utils.review_note_v2()])
        r = Adapter.to_human_reviews(cache)[0]
        assert r.reviewer_id == "Reviewer_xyz"
        assert r.summary == "S2" and r.full_text == "R2"
        assert r.rating == 8 and r.confidence == 5

    def test_ignores_non_review_notes(self):
        cache = OpenReviewCache.from_notes([
            {"id": "d", "invitation": "ICLR/-/Decision", "content": {"decision": "Accept"}},
            {"id": "m", "invitation": "ICLR/-/Meta_Review", "content": {"metareview": "x"}},
        ])
        assert Adapter.to_human_reviews(cache) == []


class TestHumanMetaReview:
    def test_parses_v1_meta_review(self):
        cache = OpenReviewCache.from_notes([
            {"id": "m1", "invitation": "ICLR/-/Meta_Review",
             "content": {"metareview": "Solid but revise.", "recommendation": "Accept"}},
        ])
        meta = Adapter.to_human_meta_review(cache)
        assert isinstance(meta, HumanMetaReview)
        assert meta.note_id == "m1"
        assert meta.text == "Solid but revise."
        assert meta.recommendation == "Accept"

    def test_none_when_absent(self):
        cache = OpenReviewCache.from_notes([Utils.review_note_v1()])
        assert Adapter.to_human_meta_review(cache) is None


class TestDecision:
    def test_parses_decision_note(self):
        cache = OpenReviewCache.from_notes([
            {"id": "dec", "invitation": "ICLR/-/Decision", "content": {"decision": "Accept (Poster)"}},
        ])
        assert Adapter.to_open_review_decision(cache) == "Accept (Poster)"

    def test_v2_decision_value_wrapped(self):
        cache = OpenReviewCache.from_notes([
            {"id": "dec", "invitations": ["ICLR/-/Decision"], "content": {"decision": {"value": "Reject"}}},
        ])
        assert Adapter.to_open_review_decision(cache) == "Reject"

    def test_none_when_absent(self):
        cache = OpenReviewCache.from_notes([Utils.review_note_v1()])
        assert Adapter.to_open_review_decision(cache) is None


class TestFactory:
    def test_to_rag_index_record_roundtrips(self):
        record = Factory.to_rag_index_record(Utils.rag_index())
        assert isinstance(record, StoreRagIndex)
        assert record.doc_id == "d1"
        assert len(record.sections) == 2

    def test_to_open_review_cache_record_roundtrips(self):
        cache = OpenReviewCache.from_notes([Utils.review_note_v1()])
        record = Factory.to_open_review_cache_record(cache)
        assert isinstance(record, StoreOpenReviewCache)
        assert len(record.notes) == 1
