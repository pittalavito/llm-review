"""Domain model for the local files store: a paper file under the papers root.
Files are stored with the ``paper_id`` (``<paper-type>_<name>_<extension>``) as
their file name, so the id is all callers ever see — the actual path stays an
implementation detail of the files store."""
from pydantic import BaseModel


class StoredPaper(BaseModel):
    """A paper file on the local filesystem, under the papers root."""
    paper_id: str
    size: int
    mtime_ns: int
