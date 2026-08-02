"""Unit tests for the /paper controller models — the controller -> domain
conversion of the OpenReview create request. The file_bytes round-trip is the
critical one: Base64Bytes re-encodes on model_dump(), so a naive conversion
would store base64 text instead of the PDF."""
import base64

from models.controller.paper import CreateOpenReviewPaperRequest


def _request(pdf: bytes) -> CreateOpenReviewPaperRequest:
    return CreateOpenReviewPaperRequest(
        conference="ICLR",
        forum_id="F1",
        paper_name="Great Paper",
        file_bytes=base64.b64encode(pdf),  # as it travels in the JSON body
        authors=[{"full_name": "Ada", "openreview_profile_id": "~a1", "position": 1}],
        human_decision="Accept",
        notes=[{"id": "F1", "content": {}}],
    )


class TestToDomain:
    def test_file_bytes_survive_unencoded(self):
        pdf = b"%PDF-1.7 fake body"
        domain = _request(pdf).to_domain()
        assert domain.file_bytes == pdf  # NOT base64 re-encoded
        assert domain.file_bytes.startswith(b"%PDF")

    def test_fields_map_one_to_one(self):
        domain = _request(b"%PDF-1.7").to_domain()
        assert (domain.conference, domain.forum_id, domain.paper_name) == ("ICLR", "F1", "Great Paper")
        assert domain.human_decision == "Accept"
        assert domain.authors[0].full_name == "Ada"
        assert domain.authors[0].position == 1
        assert domain.notes == [{"id": "F1", "content": {}}]
