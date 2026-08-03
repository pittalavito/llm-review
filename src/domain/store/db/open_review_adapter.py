import re
from datetime import datetime

from models.domain.openreview import OpenReviewNotes
from models.domain.comparator import HumanReview, HumanMetaReview
from models.store.db import OpenReviewTable


class OpenReviewAdapter:

    _REVIEW_KW = {"official_review", "official review"}
    _META_KW = {"meta_review", "meta review", "metareview"}
    _DECISION_KW = {"decision"}

    @staticmethod
    def from_notes(notes: OpenReviewNotes, paper_id: str) -> list[OpenReviewTable]:
        records = []
        now = datetime.utcnow().isoformat()

        reviewer_count = {}  

        for note in notes.to_notes():
            invitation = OpenReviewAdapter._invitation_text(note)
            content = OpenReviewAdapter._unwrap(note.get("content", {}))
            note_id = note.get("id", "")
            reviewer_id = str((note.get("signatures") or ["?"])[0]).split("/")[-1]

            if any(kw in invitation for kw in OpenReviewAdapter._REVIEW_KW):
                idx = reviewer_count.get("reviewer", 0) + 1
                reviewer_count["reviewer"] = idx

                record = OpenReviewTable(
                    paper_id=paper_id,
                    note_id=note_id,
                    reviewer_type="reviewer",
                    reviewer_id=reviewer_id,
                    reviewer_index=idx,
                    rating=OpenReviewAdapter._extract_int(
                        OpenReviewAdapter._get(content, "rating", "recommendation")
                    ),
                    confidence=OpenReviewAdapter._extract_int(
                        OpenReviewAdapter._get(content, "confidence")
                    ),
                    summary=OpenReviewAdapter._get(content, "summary_of_the_paper", "summary"),
                    significance_and_novelty=OpenReviewAdapter._get(content, "strengths", "strength_and_weaknesses"),
                    review_text=OpenReviewAdapter._get(content, "review", "main_review"),
                    created_at=now,
                    updated_at=now,
                )
                records.append(record)

            elif any(kw in invitation for kw in OpenReviewAdapter._META_KW):
                # Meta-reviewer
                record = OpenReviewTable(
                    paper_id=paper_id,
                    note_id=note_id,
                    reviewer_type="meta_reviewer",
                    reviewer_index=None,
                    overall_score=OpenReviewAdapter._extract_int(
                        OpenReviewAdapter._get(content, "metareview_score", "overall_score")
                    ),
                    recommendation=OpenReviewAdapter._get(content, "recommendation", "decision"),
                    summary=OpenReviewAdapter._get(content, "metareview", "meta_review", "comment", "summary"),
                    created_at=now,
                    updated_at=now,
                )
                records.append(record)

            elif any(kw in invitation for kw in OpenReviewAdapter._DECISION_KW):
                # Area Chair decision
                record = OpenReviewTable(
                    paper_id=paper_id,
                    note_id=note_id,
                    reviewer_type="area_chair",
                    reviewer_index=None,
                    confidence=OpenReviewAdapter._extract_int(
                        OpenReviewAdapter._get(content, "confidence")
                    ),
                    decision=OpenReviewAdapter._get(content, "decision", "recommendation"),
                    summary=OpenReviewAdapter._get(content, "summary", "comment"),
                    justification=OpenReviewAdapter._get(content, "justification", "comment"),
                    created_at=now,
                    updated_at=now,
                )
                records.append(record)

        return records

    @staticmethod
    def _invitation_text(note: dict) -> str:
        """Lowercased invitation, handling v1 (str) and v2 (list)."""
        raw = note.get("invitation") or note.get("invitations") or ""
        if isinstance(raw, (list, tuple)):
            raw = " ".join(str(x) for x in raw)
        return str(raw).lower()

    @staticmethod
    def _unwrap(content: dict) -> dict:
        """OpenReview v2 unwrap: flatten {"value": ...} to value."""
        return {
            k: (v["value"] if isinstance(v, dict) and "value" in v else v)
            for k, v in content.items()
        }

    @staticmethod
    def _get(content: dict, *keys: str) -> str | None:
        """Get first available key from content."""
        for key in keys:
            value = content.get(key)
            if value:
                return value if isinstance(value, str) else str(value)
        return None

    @staticmethod
    def _extract_int(value: object) -> int | None:
        """Extract leading integer (e.g., '6: marginally above...')."""
        if value is None:
            return None
        m = re.match(r"(\d+)", str(value).strip())
        return int(m.group(1)) if m else None

    @staticmethod
    def to_human_review(row: OpenReviewTable) -> HumanReview:
        """Convert a reviewer OpenReviewTable row to HumanReview domain model."""
        return HumanReview(
            note_id=row.note_id,
            reviewer_id=row.reviewer_id or "",
            summary=row.summary,
            strengths=row.significance_and_novelty,
            full_text=row.review_text,
            rating=row.rating,
            confidence=row.confidence,
        )

    @staticmethod
    def to_human_meta_review(row: OpenReviewTable) -> HumanMetaReview:
        """Convert a meta-reviewer OpenReviewTable row to HumanMetaReview domain model."""
        return HumanMetaReview(
            note_id=row.note_id,
            text=row.summary,
            recommendation=row.recommendation,
        )

    @staticmethod
    def to_human_reviews_from_rows(rows: list[OpenReviewTable]) -> list[HumanReview]:
        """Convert reviewer rows to HumanReview models."""
        return [
            OpenReviewAdapter.to_human_review(row)
            for row in rows
            if row.reviewer_type == "reviewer"
        ]

    @staticmethod
    def to_human_meta_reviews_from_rows(rows: list[OpenReviewTable]) -> HumanMetaReview | None:
        """Get meta-review from rows, if present."""
        for row in rows:
            if row.reviewer_type == "meta_reviewer":
                return OpenReviewAdapter.to_human_meta_review(row)
        return None
