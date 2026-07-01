"""RAG document manifest — tracks which files are indexed and when.

Written to ``<project>/.agentx/rag_manifest.json`` after every successful
index build.  Enables:
  * Incremental re-indexing (only re-embed files whose content hash changed).
  * Auditability — one place to see what the vector store contains.
  * Reproducibility — a small artifact that can be committed alongside code.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class DocumentEntry:
    """One document tracked in the manifest."""

    filename: str
    sha256: str
    size_bytes: int
    indexed_at: str
    chunk_count: int = 0


@dataclass
class Manifest:
    """The manifest for a single RAG index."""

    vector_store: str = "chroma"
    embedding_provider: str = ""
    embedding_model: str = ""
    total_chunks: int = 0
    documents: dict[str, DocumentEntry] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        return {
            "vector_store": self.vector_store,
            "embedding_provider": self.embedding_provider,
            "embedding_model": self.embedding_model,
            "total_chunks": self.total_chunks,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "documents": {name: asdict(e) for name, e in self.documents.items()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Manifest":
        m = cls(
            vector_store=data.get("vector_store", "chroma"),
            embedding_provider=data.get("embedding_provider", ""),
            embedding_model=data.get("embedding_model", ""),
            total_chunks=data.get("total_chunks", 0),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )
        for name, entry in (data.get("documents") or {}).items():
            m.documents[name] = DocumentEntry(**entry)
        return m


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def hash_file(path: str | Path, chunk_bytes: int = 65536) -> str:
    """Return the SHA-256 hex digest of a file's content."""
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for block in iter(lambda: fh.read(chunk_bytes), b""):
            h.update(block)
    return h.hexdigest()


def load_manifest(path: str | Path) -> Manifest:
    """Load a manifest from disk. Returns an empty ``Manifest`` if missing."""
    p = Path(path)
    if not p.exists():
        return Manifest(created_at=_now(), updated_at=_now())
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return Manifest.from_dict(data)
    except (json.JSONDecodeError, TypeError, KeyError) as exc:
        logger.warning("Manifest at %s is corrupt (%s); starting fresh.", p, exc)
        return Manifest(created_at=_now(), updated_at=_now())


def save_manifest(manifest: Manifest, path: str | Path) -> None:
    """Write ``manifest`` to disk atomically (temp file + replace)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    manifest.updated_at = _now()
    if not manifest.created_at:
        manifest.created_at = manifest.updated_at
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(manifest.to_dict(), indent=2) + "\n", encoding="utf-8")
    tmp.replace(p)
    logger.debug("Manifest saved to %s (%d documents)", p, len(manifest.documents))


def diff_directory(
    directory: str | Path,
    manifest: Manifest,
    supported_exts: set[str] | None = None,
) -> tuple[list[Path], list[Path], list[str]]:
    """Compare the on-disk directory against the manifest.

    Returns:
        (added, changed, removed)
        * added   — Paths present on disk but not in the manifest.
        * changed — Paths present in both but whose content hash differs.
        * removed — Filenames in the manifest that no longer exist on disk.
    """
    supported = supported_exts or {
        ".pdf", ".xlsx", ".xls", ".xlsm", ".csv", ".docx",
        ".txt", ".md", ".markdown", ".rst",
    }
    d = Path(directory)
    on_disk: dict[str, Path] = {
        p.name: p
        for p in d.rglob("*")
        if p.is_file()
        and p.suffix.lower() in supported
        and p.name != "README.md"
        and not p.name.startswith(".")
    }

    added: list[Path] = []
    changed: list[Path] = []

    for name, path in on_disk.items():
        entry = manifest.documents.get(name)
        if entry is None:
            added.append(path)
            continue
        try:
            new_hash = hash_file(path)
        except OSError:
            continue
        if new_hash != entry.sha256:
            changed.append(path)

    removed = [name for name in manifest.documents if name not in on_disk]

    return added, changed, removed


def build_document_entry(path: str | Path, chunk_count: int = 0) -> DocumentEntry:
    """Build a ``DocumentEntry`` from a file path."""
    p = Path(path)
    return DocumentEntry(
        filename=p.name,
        sha256=hash_file(p),
        size_bytes=p.stat().st_size,
        indexed_at=_now(),
        chunk_count=chunk_count,
    )
