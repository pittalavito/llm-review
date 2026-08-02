"""OpenReview notes knowledge — pure helpers over the verbatim ``notes`` array
of a forum response (v1 and v2 shapes).

No HTTP here: openreview.net sits behind a bot challenge, so the PDF (and the
notes JSON itself) are fetched by the user's browser and shipped by the FE.
"""
from core.error import ValidationError


class NotesAdapter:
    """Pure helpers over the verbatim ``notes`` array of a forum response."""

    @staticmethod
    def forum_note(forum_id: str, notes: list[dict]) -> dict:
        """The forum note — the submission itself: matched by id, else the
        note without a ``replyto``. ValidationError when absent."""
        note = (
            next((n for n in notes if n.get("id") == forum_id), None)
            or next((n for n in notes if not n.get("replyto")), None)
        )
        if note is None:
            raise ValidationError("No forum note found in the notes payload.")
        return note

    @staticmethod
    def api_version(note: dict) -> str:
        """"v2" when the note carries the ``invitations`` list, "v1" otherwise."""
        return "v2" if isinstance(note.get("invitations"), list) else "v1"

    @staticmethod
    def unwrap_value(value: object) -> object:
        """OpenReview v2 wraps content fields as ``{"value": ...}``; flatten."""
        return value.get("value") if isinstance(value, dict) and "value" in value else value
