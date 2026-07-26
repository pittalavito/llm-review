"""Unit tests for the retrieval domain (domain/retrieval/base.py): IndexBuilder
section grouping and PaperFileReader path resolution / .txt extraction / section
walking. The PDF/Docling path is not exercised here (no torch dependency needed)."""
import pytest

from core.error import NotFoundError, ValidationError
from domain.models.retrieval import RagFileSignature, RagIndex
from domain.retrieval.base import IndexBuilder, PaperFileReader


def _signature() -> RagFileSignature:
    return RagFileSignature(mtime_ns=1, size=2)


class _FakeItem:
    def __init__(self, text: str, label: str = "text"):
        self.text = text
        self.label = label


class _FakeDocument:
    """Duck-typed Docling document: yields (item, level) from iterate_items."""
    def __init__(self, items: list[_FakeItem]):
        self._items = items

    def iterate_items(self):
        for item in self._items:
            yield item, 0


class TestIndexBuilder:
    def test_groups_bodies_by_heading_preserving_order(self):
        raw = [("Intro", "hello"), ("Methods", "a"), ("Methods", "b")]
        index = IndexBuilder("v1").build_index(raw, "p.txt", "doc1", _signature())
        assert isinstance(index, RagIndex)
        assert [s.name for s in index.sections] == ["Intro", "Methods"]
        assert index.sections[1].text == "a b"  # bodies joined
        assert index.settings.strategy_version == "v1"
        assert index.doc_id == "doc1" and index.paper_path == "p.txt"

    def test_cleans_heading_whitespace(self):
        index = IndexBuilder("v1").build_index([("  Related   Work \n", "x")], "p.txt", "d", _signature())
        assert index.sections[0].name == "Related Work"

    def test_empty_raw_sections_raises(self):
        with pytest.raises(ValidationError):
            IndexBuilder("v1").build_index([], "p.txt", "d", _signature())

    def test_all_empty_bodies_raises(self):
        with pytest.raises(ValidationError):
            IndexBuilder("v1").build_index([("Intro", "   "), ("Methods", "")], "p.txt", "d", _signature())


class TestResolvePaperPath:
    def _reader(self, tmp_path) -> tuple[PaperFileReader, object]:
        papers = tmp_path / "papers"
        papers.mkdir()
        return PaperFileReader(papers), papers

    def test_resolves_valid_txt(self, tmp_path):
        reader, papers = self._reader(tmp_path)
        (papers / "paper.txt").write_text("content", encoding="utf-8")
        candidate, relative = reader.resolve_paper_path("paper.txt")
        assert candidate == (papers / "paper.txt").resolve()
        assert relative == "paper.txt"

    def test_rejects_path_traversal(self, tmp_path):
        reader, _ = self._reader(tmp_path)
        with pytest.raises(ValidationError):
            reader.resolve_paper_path("../secret.txt")

    def test_missing_file_raises_not_found(self, tmp_path):
        reader, _ = self._reader(tmp_path)
        with pytest.raises(NotFoundError):
            reader.resolve_paper_path("missing.txt")

    def test_rejects_unsupported_extension(self, tmp_path):
        reader, papers = self._reader(tmp_path)
        (papers / "paper.md").write_text("x", encoding="utf-8")
        with pytest.raises(ValidationError):
            reader.resolve_paper_path("paper.md")


class TestExtractAndSignature:
    def test_extract_txt_is_single_body(self, tmp_path):
        source = tmp_path / "p.txt"
        source.write_text("  the whole paper  ", encoding="utf-8")
        assert PaperFileReader(tmp_path).extract_structure(source) == [("body", "the whole paper")]

    def test_extract_empty_txt_raises(self, tmp_path):
        source = tmp_path / "p.txt"
        source.write_text("   ", encoding="utf-8")
        with pytest.raises(ValidationError):
            PaperFileReader(tmp_path).extract_structure(source)

    def test_build_file_signature(self, tmp_path):
        source = tmp_path / "p.txt"
        source.write_text("abcde", encoding="utf-8")
        sig = PaperFileReader.build_file_signature(source)
        assert isinstance(sig, RagFileSignature)
        assert sig.size == 5 and sig.mtime_ns > 0


class TestWalkDocumentSections:
    def test_groups_items_under_headings(self):
        document = _FakeDocument([
            _FakeItem("Intro", "section_header"),
            _FakeItem("hello"),
            _FakeItem("Methods", "title"),
            _FakeItem("world"),
        ])
        assert PaperFileReader._walk_document_sections(document) == [("Intro", "hello"), ("Methods", "world")]

    def test_no_headers_collapses_to_single_body(self):
        document = _FakeDocument([_FakeItem("a"), _FakeItem("b")])
        assert PaperFileReader._walk_document_sections(document) == [("body", "a b")]

    def test_keeps_empty_bodied_heading_markers(self):
        document = _FakeDocument([_FakeItem("Appendix", "section_header")])
        assert PaperFileReader._walk_document_sections(document) == [("Appendix", "")]
