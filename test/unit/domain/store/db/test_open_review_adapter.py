"""Unit tests for the OpenReview note parser (domain/store/db/open_review_adapter.py):
notes (v1 flat content + v2 {"value": ...} wrapping) -> OpenReviewTable rows ->
HumanReview / HumanMetaReview. Successor of the parsing that used to live in
the Redis store. No database involved."""
from domain.store.db.open_review_adapter import OpenReviewAdapter
from models.domain.comparator import HumanMetaReview, HumanReview
from models.domain.openreview import OpenReviewNotes


class Utils:
    """Static note fixtures (v1 flat and v2 value-wrapped shapes)."""

    @staticmethod
    def review_note_v1() -> dict:
        return {
            "id": "n1", "invitation": "ICLR.cc/2024/-/Official_Review",
            "signatures": ["ICLR.cc/2024/Reviewer_abc"],
            "content": {
                "summary_of_the_paper": "S", "strength_and_weaknesses": "SW",
                "main_review": "MR", "rating": "6: marginally above the acceptance threshold",
                "confidence": "4: confident",
            },
        }

    @staticmethod
    def review_note_v2() -> dict:
        return {
            "id": "n2", "invitations": ["ICLR.cc/2024/-/Official_Review"],
            "signatures": ["ICLR.cc/2024/Reviewer_xyz"],
            "content": {
                "summary": {"value": "S2"}, "review": {"value": "R2"},
                "strengths": {"value": "solid"},
                "rating": {"value": "8: top 50%"}, "confidence": {"value": "5"},
            },
        }

    @staticmethod
    def meta_review_note() -> dict:
        return {
            "id": "m1", "invitation": "ICLR/-/Meta_Review", "signatures": ["ICLR/Area_Chair1"],
            "content": {"metareview": "Solid but revise.", "recommendation": "Accept"},
        }

    @staticmethod
    def decision_note() -> dict:
        return {
            "id": "dec", "invitation": "ICLR/-/Decision", "signatures": ["ICLR/Program_Chairs"],
            "content": {"decision": "Accept (Poster)"},
        }

    @staticmethod
    def rows(*notes: dict) -> list:
        return OpenReviewAdapter.from_notes(OpenReviewNotes.from_notes(list(notes)), "p1")


class TestParserHelpers:
    def test_extract_int_leading_number(self):
        assert OpenReviewAdapter._extract_int("6: marginally above") == 6
        assert OpenReviewAdapter._extract_int("5") == 5
        assert OpenReviewAdapter._extract_int(7) == 7

    def test_extract_int_none_and_no_digits(self):
        assert OpenReviewAdapter._extract_int(None) is None
        assert OpenReviewAdapter._extract_int("no digits here") is None

    def test_unwrap_flattens_only_value_dicts(self):
        assert OpenReviewAdapter._unwrap({"a": {"value": 1}, "b": 2, "c": {"nested": 3}}) == {"a": 1, "b": 2, "c": {"nested": 3}}

    def test_invitation_text_handles_v1_str_and_v2_list(self):
        assert OpenReviewAdapter._invitation_text({"invitation": "X/Official_Review"}) == "x/official_review"
        assert OpenReviewAdapter._invitation_text({"invitations": ["A", "B"]}) == "a b"
        assert OpenReviewAdapter._invitation_text({}) == ""

    def test_get_returns_first_nonempty_and_coerces_to_str(self):
        assert OpenReviewAdapter._get({"a": "", "b": "x"}, "a", "b") == "x"
        assert OpenReviewAdapter._get({"n": 5}, "n") == "5"
        assert OpenReviewAdapter._get({}, "missing") is None


class TestFromNotes:
    def test_parses_v1_flat_review_note(self):
        rows = Utils.rows(Utils.review_note_v1())
        assert len(rows) == 1
        row = rows[0]
        assert (row.paper_id, row.note_id, row.reviewer_type) == ("p1", "n1", "reviewer")
        assert row.reviewer_id == "Reviewer_abc"  # last signature segment
        assert row.reviewer_index == 1
        assert (row.summary, row.significance_and_novelty, row.review_text) == ("S", "SW", "MR")
        assert (row.rating, row.confidence) == (6, 4)

    def test_parses_v2_value_wrapped_review_note(self):
        row = Utils.rows(Utils.review_note_v2())[0]
        assert row.reviewer_id == "Reviewer_xyz"
        assert (row.summary, row.significance_and_novelty, row.review_text) == ("S2", "solid", "R2")
        assert (row.rating, row.confidence) == (8, 5)

    def test_reviewer_indexes_count_up(self):
        rows = Utils.rows(Utils.review_note_v1(), Utils.review_note_v2())
        assert [row.reviewer_index for row in rows] == [1, 2]

    def test_parses_meta_review_note(self):
        row = Utils.rows(Utils.meta_review_note())[0]
        assert (row.reviewer_type, row.reviewer_index) == ("meta_reviewer", None)
        assert row.summary == "Solid but revise."
        assert row.recommendation == "Accept"

    def test_parses_decision_note(self):
        row = Utils.rows(Utils.decision_note())[0]
        assert (row.reviewer_type, row.reviewer_index) == ("area_chair", None)
        assert row.decision == "Accept (Poster)"

    def test_ignores_unrelated_notes(self):
        assert Utils.rows({"id": "c", "invitation": "ICLR/-/Comment", "content": {"comment": "hi"}}) == []


class TestToHumanModels:
    def test_to_human_reviews_from_rows_keeps_only_reviewers(self):
        rows = Utils.rows(Utils.review_note_v1(), Utils.meta_review_note(), Utils.decision_note())
        reviews = OpenReviewAdapter.to_human_reviews_from_rows(rows)
        assert len(reviews) == 1
        review = reviews[0]
        assert isinstance(review, HumanReview)
        assert review.reviewer_id == "Reviewer_abc"
        assert (review.summary, review.strengths, review.full_text) == ("S", "SW", "MR")
        assert (review.rating, review.confidence) == (6, 4)

    def test_to_human_meta_reviews_from_rows(self):
        rows = Utils.rows(Utils.review_note_v1(), Utils.meta_review_note())
        meta = OpenReviewAdapter.to_human_meta_reviews_from_rows(rows)
        assert isinstance(meta, HumanMetaReview)
        assert (meta.note_id, meta.text, meta.recommendation) == ("m1", "Solid but revise.", "Accept")

    def test_to_human_meta_reviews_none_when_absent(self):
        rows = Utils.rows(Utils.review_note_v1())
        assert OpenReviewAdapter.to_human_meta_reviews_from_rows(rows) is None
