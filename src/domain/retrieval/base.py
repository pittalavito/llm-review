"""Retrieval domain: turn a paper file into a per-paper RagIndex of full-text
sections. ``PaperFileReader`` resolves and reads the file (``.txt`` verbatim,
``.pdf`` via Docling's layout parser) into (heading, body) pairs;
``IndexBuilder`` groups those into the domain ``RagIndex``. No chunking/BM25 —
the whole paper is stored so every agent reviews the complete work."""
from pathlib import Path

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from core.error import NotFoundError, ValidationError
from domain.models.retrieval import RagFileSignature, RagIndex, RagIndexConfig, RagSectionEntry

_ALLOWED_EXTENSIONS = {".txt", ".pdf"}
_HEADER_LABEL_VALUES = {"section_header", "title"}


class IndexBuilder:
    """Turns the (heading, body) pairs extracted from a paper into a per-paper
    ``RagIndex`` of full-text sections."""

    def __init__(self, strategy_version: str):
        self._strategy_version = strategy_version

    def build_index(self, raw_sections: list[tuple[str, str]], relative_path: str, doc_id: str, file_signature: RagFileSignature) -> RagIndex:
        if not raw_sections:
            raise ValidationError("The extracted document text is empty.")

        section_bodies: dict[str, list[str]] = {}
        for heading, body_text in raw_sections:
            name = IndexBuilder._clean_heading(heading)
            section_bodies.setdefault(name, [])
            if body_text.strip():
                section_bodies[name].append(body_text)

        sections = [
            RagSectionEntry(name=name, text=" ".join(bodies).strip())
            for name, bodies in section_bodies.items()
            if any(body.strip() for body in bodies)
        ]

        if not sections:
            raise ValidationError("Unable to build any section from the given file.")

        return RagIndex(
            doc_id=doc_id,
            paper_path=relative_path,
            file_signature=file_signature,
            settings=RagIndexConfig(strategy_version=self._strategy_version),
            sections=sections,
        )

    @staticmethod
    def _clean_heading(raw: str) -> str:
        """Whitespace-normalize a raw heading for use as a section name (kept
        verbatim, any language — no canonical mapping)."""
        return " ".join(raw.split())


class PaperFileReader:
    """Resolves a paper path (safely, under ``papers_dir``) and extracts its
    (heading, body) sections. The Docling converter is built once, on the first
    PDF, and reused."""

    def __init__(self, papers_dir: Path):
        self.papers_dir = papers_dir.resolve()
        self._converter = None

    def resolve_paper_path(self, paper_path: str) -> tuple[Path, str]:
        normalized = paper_path.replace("\\", "/").strip("/")
        candidate = (self.papers_dir / normalized).resolve()

        if self.papers_dir not in candidate.parents and candidate != self.papers_dir:
            raise ValidationError("Invalid paper path: path traversal is not allowed.")
        if not candidate.exists() or not candidate.is_file():
            raise NotFoundError(f"Paper file not found: {normalized}")
        if candidate.suffix.lower() not in _ALLOWED_EXTENSIONS:
            raise ValidationError("Unsupported file type. Use .txt or .pdf files.")

        relative_path = candidate.relative_to(self.papers_dir).as_posix()
        return candidate, relative_path

    def extract_structure(self, source_path: Path) -> list[tuple[str, str]]:
        """Return (heading, body_text) pairs in document order.

        ``.txt`` files have no layout to parse: the whole file becomes one
        "body" section. ``.pdf`` files are parsed with Docling, which detects
        real section headings from the document's actual layout — independent of
        language or heading wording, unlike guessing from flat extracted text.
        """
        if source_path.suffix.lower() == ".txt":
            return self._read_txt(source_path)

        document = self._converter_for_pdf().convert(str(source_path)).document
        sections = self._walk_document_sections(document)
        if not sections:
            raise ValidationError("Could not extract text from the selected paper file.")
        return sections

    @staticmethod
    def build_file_signature(source_path: Path) -> RagFileSignature:
        source_stat = source_path.stat()
        return RagFileSignature(mtime_ns=source_stat.st_mtime_ns, size=source_stat.st_size)

    @staticmethod
    def _read_txt(source_path: Path) -> list[tuple[str, str]]:
        text = source_path.read_text(encoding="utf-8").strip()
        if not text:
            raise ValidationError("Could not extract text from the selected paper file.")
        return [("body", text)]

    def _converter_for_pdf(self):
        """Lazily build and cache one Docling converter tuned for speed: OCR and
        table-structure detection are disabled (pure waste on digital academic
        PDFs — we only need the heading/paragraph layout), and the converter is
        built once and reused for the whole corpus. Docling is imported here
        (not at module top) because it drags in torch/transformers — a
        multi-second import the non-PDF paths must skip."""
        if self._converter is None:
            options = PdfPipelineOptions()
            options.do_ocr = False
            options.do_table_structure = False
            self._converter = DocumentConverter(
                format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
            )
        return self._converter

    @staticmethod
    def _walk_document_sections(document) -> list[tuple[str, str]]:
        """Group Docling's flat item stream into (heading, body) sections. Every
        non-header item accumulates under the current heading; a header flushes
        the current section and opens a new one. Headers with no body of their
        own are kept (empty body). A document with no detected headers collapses
        to a single "body" section."""
        sections: list[tuple[str, str]] = []
        heading = "preamble"
        buffer: list[str] = []
        saw_header = False

        def flush() -> None:
            sections.append((heading, " ".join(buffer).strip()))

        for item, _level in document.iterate_items():
            text = getattr(item, "text", None)
            if not text:
                continue
            if str(getattr(item, "label", "")) in _HEADER_LABEL_VALUES:
                flush()
                heading, buffer = text, []
                saw_header = True
            else:
                buffer.append(text)
        flush()

        if not saw_header:
            full_text = " ".join(body for _, body in sections if body)
            return [("body", full_text)] if full_text else []

        return [(head, body) for head, body in sections if body or head != "preamble"]
