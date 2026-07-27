"""Domain model for the local files store: a paper file under the papers root.
The ``relative_path`` (posix, relative to the root) is the id used everywhere."""
from pydantic import BaseModel


class StoredPaper(BaseModel):
    """A paper file on the local filesystem, under the papers root."""
    relative_path: str
    name: str
    size: int
    mtime_ns: int
