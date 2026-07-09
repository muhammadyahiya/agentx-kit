"""Shared workspace path-sandboxing helper for agents that touch a filesystem."""
from __future__ import annotations

from pathlib import Path


def safe_join(workspace: Path, filename: str) -> Path:
    """Resolve ``filename`` under ``workspace`` and reject escape attempts.

    Returns a path guaranteed to be inside ``workspace``.  Raises ValueError
    otherwise so the LLM sees the error and can retry.
    """
    if not filename or not filename.strip():
        raise ValueError("filename must not be empty")
    # Reject absolute paths outright.
    candidate = Path(filename)
    if candidate.is_absolute():
        raise ValueError(f"absolute paths are not allowed: {filename!r}")
    resolved = (workspace / candidate).resolve()
    ws_resolved = workspace.resolve()
    try:
        resolved.relative_to(ws_resolved)
    except ValueError as exc:
        raise ValueError(
            f"path escapes workspace: {filename!r} → {resolved} not under {ws_resolved}"
        ) from exc
    return resolved
