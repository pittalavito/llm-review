"""Retrieval domain: read a paper file into (heading, body) sections and build a
strategy-specific RagIndex, then produce the context text handed to an agent for
a query.

``PaperFileReader`` parses the file ("txt" verbatim, "pdf" via Docling layout
parsing; the format comes from the paper_id, files carry no dot-extension).
``RetrievalStrategy`` is the pluggable seam — pick one
with ``RetrievalStrategy.create(strategy, ...)``:
  - ``FullContextStrategy``: whole paper, all sections concatenated (query ignored);
  - ``Bm25Strategy``: chunk the paper, rank chunks by BM25 lexical score;
  - ``EmbeddingStrategy``: chunk the paper, rank chunks by embedding cosine similarity;
  - ``SummaryStrategy``: one LLM-generated summary of the whole paper (query ignored).
Chunk-based strategies share ``Chunker``; the embedding strategy uses an
``Embedder`` (``MockEmbedder`` for tests; a real provider plugs in behind the seam);
the summary strategy uses a ``Summarizer`` (``ChatSummarizer`` over an injected Chat).
"""
import re
from abc import ABC, abstractmethod
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING
from zlib import crc32

from docling.datamodel.base_models import DocumentStream, InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from rank_bm25 import BM25Okapi

from core.error import ValidationError
from models.domain.chat import SummaryResponseSchema
from models.domain.retrieval import RagChunk, RagFileSignature, RagIndex, RagIndexConfig, RagSectionEntry, RagStrategy, RagTokenUsage, SummaryResult

if TYPE_CHECKING:
    from domain.chat.base import Chat

_HEADER_LABEL_VALUES = {"section_header", "title"}


class PaperFileReader:
    """Parses a paper file into (heading, body) sections. Resolving/reading the
    file is the files store's job — this reader only parses a given path, with
    the format ("txt" verbatim, "pdf" via Docling) passed in by the caller since
    files are named by paper_id and carry no dot-extension. The Docling
    converter is built once, on the first PDF, and reused."""

    def __init__(self):
        self._converter = None

    def extract_structure(self, source_path: Path, file_format: str) -> list[tuple[str, str]]:
        """Return (heading, body_text) pairs in document order. "txt" becomes a
        single "body" section; "pdf" is parsed with Docling's layout detector."""
        if file_format == "txt":
            return self._read_txt(source_path)

        stream = DocumentStream(name=f"{source_path.name}.pdf", stream=BytesIO(source_path.read_bytes()))
        document = self._converter_for_pdf().convert(stream).document
        sections = self._walk_document_sections(document)
        if not sections:
            raise ValidationError("Could not extract text from the selected paper file.")
        return sections

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
        built once and reused for the whole corpus."""
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
        """Group Docling's flat item stream into (heading, body) sections. A
        header flushes the current section and opens a new one; a document with
        no detected headers collapses to a single "body" section. Items made of
        digits only are dropped: they are margin line numbers (ICLR/NeurIPS
        submission PDFs number every line), not content."""
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
            if re.fullmatch(r"[\d\s]+", text):
                continue  # margin line numbers / page numbers
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


class Chunker:
    """Splits sections into overlapping chunks that respect sentence boundaries
    (word boundaries for oversized sentences), tagging each chunk with its source
    section. ``chunk_size``/``overlap`` are character budgets: a chunk holds as
    many whole sentences as fit in ``chunk_size``, and the next chunk is seeded
    with the trailing sentences of the previous one up to ``overlap`` chars — so
    a chunk never cuts mid-word and spans at most ``chunk_size + overlap``."""

    _EXCLUDED_SECTIONS = {"references", "bibliography", "acknowledgments", "acknowledgements"}
    """Sections that never make good retrieval context: lexically dense (they
    match almost any query under BM25) and content-free for reviewing."""

    def __init__(self, chunk_size: int = 1000, overlap: int = 150):
        self._chunk_size = chunk_size
        self._overlap = overlap

    def chunk(self, sections: list[RagSectionEntry]) -> list[RagChunk]:
        chunks: list[RagChunk] = []
        for section in sections:
            if section.name.strip().lower() in self._EXCLUDED_SECTIONS:
                continue
            for piece in self._split(section.text):
                chunks.append(RagChunk(text=piece, section=section.name))
        return chunks

    def _split(self, text: str) -> list[str]:
        text = " ".join(text.split())
        if not text:
            return []
        chunks: list[str] = []
        current: list[str] = []
        current_len = 0
        for piece in self._pieces(text):
            extra = len(piece) + (1 if current else 0)
            if current and current_len + extra > self._chunk_size:
                chunks.append(" ".join(current))
                current = self._overlap_tail(current)
                current_len = sum(len(kept) for kept in current) + max(0, len(current) - 1)
                extra = len(piece) + (1 if current else 0)
            current.append(piece)
            current_len += extra
        if current:
            chunks.append(" ".join(current))
        return chunks

    def _pieces(self, text: str) -> list[str]:
        """Sentences; any sentence over the chunk budget is word-packed down to
        size (a single oversized word is kept whole rather than cut)."""
        pieces: list[str] = []
        for sentence in re.split(r"(?<=[.!?])\s+", text):
            if not sentence:
                continue
            if len(sentence) <= self._chunk_size:
                pieces.append(sentence)
                continue
            packed = ""
            for word in sentence.split():
                if packed and len(packed) + 1 + len(word) > self._chunk_size:
                    pieces.append(packed)
                    packed = word
                else:
                    packed = f"{packed} {word}" if packed else word
            if packed:
                pieces.append(packed)
        return pieces

    def _overlap_tail(self, pieces: list[str]) -> list[str]:
        """Trailing pieces of a flushed chunk, up to ``overlap`` chars, used to
        seed the next chunk for context continuity."""
        tail: list[str] = []
        length = 0
        for piece in reversed(pieces):
            extra = len(piece) + (1 if tail else 0)
            if length + extra > self._overlap:
                break
            tail.insert(0, piece)
            length += extra
        return tail


class Embedder(ABC):
    """Turns texts into fixed-dimension vectors. The real provider (Ollama/OpenAI
    via langchain, from config) plugs in behind this seam."""

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        ...


class MockEmbedder(Embedder):
    """Deterministic bag-of-words hashing embedder for tests — no model, no
    network. Each token is hashed (crc32) into a bucket; the vector is
    L2-normalized so cosine similarity reflects token overlap."""

    def __init__(self, dim: int = 64):
        self._dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * self._dim
        for token in text.lower().split():
            vector[crc32(token.encode()) % self._dim] += 1.0
        norm = sum(value * value for value in vector) ** 0.5
        return [value / norm for value in vector] if norm else vector


class Summarizer(ABC):
    """Produces a summary of a paper from its sections. The LLM-backed
    implementation plugs in behind this seam, mirroring the Embedder one."""

    @abstractmethod
    def summarize(self, sections: list[RagSectionEntry]) -> SummaryResult:
        ...


class ChatSummarizer(Summarizer):
    """LLM-backed summarizer over an injected ``Chat`` client. The paper text is
    truncated to ``max_input_chars`` before the call as a context-window guard."""

    SYSTEM_PROMPT = (
        "You are an expert scientific editor. Summarize the paper provided by the user "
        "into a faithful, self-contained overview covering: the problem addressed, the "
        "proposed approach, the experimental setup, the main results, and the stated "
        "limitations. Stick to what the text says; do not add opinions or external facts."
    )

    def __init__(self, chat: "Chat", max_input_chars: int = 60000):
        self._chat = chat
        self._max_input_chars = max_input_chars

    
    def summarize(self, sections: list[RagSectionEntry]) -> SummaryResult:
        paper_text = "\n\n".join(f"# {section.name}\n{section.text}" for section in sections)
        response = self._chat.invoke(
            system_prompt=self.SYSTEM_PROMPT,
            message=paper_text[: self._max_input_chars],
            response_schema=SummaryResponseSchema,
            label="summarizer",
        )
        return SummaryResult(
            summary=response.response_schema.summary,
            token_usage=RagTokenUsage(
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                total_tokens=response.total_tokens,
            ),
        )


class RetrievalStrategy(ABC):
    """Builds a strategy-specific RagIndex from the (heading, body) pairs and
    produces the context text for a query."""

    strategy: RagStrategy

    def __init__(self, strategy_version: str):
        self._strategy_version = strategy_version

    @abstractmethod
    def build_index(self, raw_sections: list[tuple[str, str]], paper_id: str, doc_id: str, file_signature: RagFileSignature) -> RagIndex:
        ...

    @abstractmethod
    def build_context(self, index: RagIndex, query: str) -> str:
        ...

    def _config(self) -> RagIndexConfig:
        return RagIndexConfig(strategy=self.strategy, strategy_version=self._strategy_version)

    @staticmethod
    def _group_sections(raw_sections: list[tuple[str, str]]) -> list[RagSectionEntry]:
        """Group (heading, body) pairs into RagSectionEntry: clean headings and
        concatenate bodies under the same heading (first-seen order)."""
        if not raw_sections:
            raise ValidationError("The extracted document text is empty.")

        section_bodies: dict[str, list[str]] = {}
        for heading, body in raw_sections:
            name = " ".join(heading.split())
            section_bodies.setdefault(name, [])
            if body.strip():
                section_bodies[name].append(body)

        sections = [
            RagSectionEntry(name=name, text=" ".join(bodies).strip())
            for name, bodies in section_bodies.items()
            if any(body.strip() for body in bodies)
        ]
        if not sections:
            raise ValidationError("Unable to build any section from the given file.")
        return sections

    @staticmethod
    def _format_chunk(chunk: RagChunk) -> str:
        return f"# {chunk.section}\n{chunk.text}" if chunk.section else chunk.text

    @staticmethod
    def create(strategy: RagStrategy, strategy_version: str, *, embedder: "Embedder | None" = None, chunker: "Chunker | None" = None, summarizer: "Summarizer | None" = None, top_k: int = 5) -> "RetrievalStrategy":
        if strategy is RagStrategy.FULL_CONTEXT:
            return FullContextStrategy(strategy_version)
        if strategy is RagStrategy.BM25:
            return Bm25Strategy(strategy_version, chunker or Chunker(), top_k)
        if strategy is RagStrategy.EMBEDDING:
            if embedder is None:
                raise ValueError("The embedding strategy requires an Embedder.")
            return EmbeddingStrategy(strategy_version, chunker or Chunker(), embedder, top_k)
        if strategy is RagStrategy.SUMMARY:
            if summarizer is None:
                raise ValueError("The summary strategy requires a Summarizer.")
            return SummaryStrategy(strategy_version, summarizer)
        raise ValueError(f"Unsupported RAG strategy: {strategy}")

    
class FullContextStrategy(RetrievalStrategy):
    """Whole paper: store every section, hand back all of them concatenated."""

    strategy = RagStrategy.FULL_CONTEXT

    def build_index(self, raw_sections, paper_id, doc_id, file_signature) -> RagIndex:
        return RagIndex(
            doc_id=doc_id, paper_id=paper_id, file_signature=file_signature,
            settings=self._config(), sections=self._group_sections(raw_sections),
        )

    def build_context(self, index: RagIndex, query: str) -> str:
        return "\n\n".join(f"# {section.name}\n{section.text}" for section in index.sections)


class Bm25Strategy(RetrievalStrategy):
    """Chunk the paper; rank chunks by BM25 lexical score against the query."""

    strategy = RagStrategy.BM25

    def __init__(self, strategy_version: str, chunker: Chunker, top_k: int = 5):
        super().__init__(strategy_version)
        self._chunker = chunker
        self._top_k = top_k

    def build_index(self, raw_sections, paper_id, doc_id, file_signature) -> RagIndex:
        chunks = self._chunker.chunk(self._group_sections(raw_sections))
        return RagIndex(
            doc_id=doc_id, paper_id=paper_id, file_signature=file_signature,
            settings=self._config(), chunks=chunks,
        )

    def build_context(self, index: RagIndex, query: str) -> str:
        chunks = index.chunks
        if not chunks:
            return ""
        bm25 = BM25Okapi([self._tokenize(chunk.text) for chunk in chunks])
        scores = bm25.get_scores(self._tokenize(query))
        top = sorted(range(len(chunks)), key=lambda i: scores[i], reverse=True)[:self._top_k]
        return "\n\n".join(self._format_chunk(chunks[i]) for i in top)

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Lowercased alphanumeric tokens — punctuation-insensitive, so
        "Attention," and "attention" score as the same term."""
        return re.findall(r"[a-z0-9]+", text.lower())


class EmbeddingStrategy(RetrievalStrategy):
    """Chunk the paper (embedding each chunk at index time); rank chunks by cosine
    similarity of the query embedding to the chunk embeddings."""

    strategy = RagStrategy.EMBEDDING

    def __init__(self, strategy_version: str, chunker: Chunker, embedder: Embedder, top_k: int = 5):
        super().__init__(strategy_version)
        self._chunker = chunker
        self._embedder = embedder
        self._top_k = top_k

    def build_index(self, raw_sections, paper_id, doc_id, file_signature) -> RagIndex:
        chunks = self._chunker.chunk(self._group_sections(raw_sections))
        for chunk, vector in zip(chunks, self._embedder.embed([chunk.text for chunk in chunks])):
            chunk.embedding = vector
        return RagIndex(
            doc_id=doc_id, paper_id=paper_id, file_signature=file_signature,
            settings=self._config(), chunks=chunks,
        )

    def build_context(self, index: RagIndex, query: str) -> str:
        chunks = [chunk for chunk in index.chunks if chunk.embedding]
        if not chunks:
            return ""
        query_vector = self._embedder.embed([query])[0]
        ranked = sorted(chunks, key=lambda chunk: self._cosine(query_vector, chunk.embedding), reverse=True)
        return "\n\n".join(self._format_chunk(chunk) for chunk in ranked[:self._top_k])

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(y * y for y in b) ** 0.5
        return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0


class SummaryStrategy(RetrievalStrategy):
    """One LLM-generated summary of the whole paper, stored as a single
    ``summary`` section (query ignored, like FullContext). The LLM cost is paid
    at index time only — serving the context is a plain cache read."""

    strategy = RagStrategy.SUMMARY

    def __init__(self, strategy_version: str, summarizer: Summarizer):
        super().__init__(strategy_version)
        self._summarizer = summarizer

    def build_index(self, raw_sections, paper_id, doc_id, file_signature) -> RagIndex:
        result = self._summarizer.summarize(self._group_sections(raw_sections))
        return RagIndex(
            doc_id=doc_id, paper_id=paper_id, file_signature=file_signature,
            settings=self._config(),
            sections=[RagSectionEntry(name="summary", text=result.summary)],
            token_usage=result.token_usage,
        )

    def build_context(self, index: RagIndex, query: str) -> str:
        return index.sections[0].text if index.sections else ""
