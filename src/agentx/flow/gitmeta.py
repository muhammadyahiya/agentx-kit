"""Per-node git history for the DAG viewer's recency/churn overlay.

Runs ``git blame`` once per file (not once per node — a project can have many
nodes per file) and slices the per-line result by each node's ``lineno``..
``end_lineno`` range to get, for free, both "how recently was this touched"
(max author date across those lines) and "how much has it churned" (number
of distinct commits across those lines) without any per-function git log
walk. Silently returns ``None`` wherever git isn't available/applicable
(not a repo, file untracked, git binary missing, etc.) — the overlay is a
nice-to-have, never a hard requirement to render the graph.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class LineBlame:
    commit: str
    author_time: int  # unix timestamp


@lru_cache(maxsize=1)
def _repo_root(start: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", start, "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def repo_root_for(file: str) -> Path | None:
    root = _repo_root(str(Path(file).resolve().parent))
    return Path(root) if root else None


def blame_file(file: str) -> dict[int, LineBlame] | None:
    """``{1-indexed line number: LineBlame}`` for every line currently in
    ``file``, or ``None`` if it can't be blamed (not a git repo, file not
    tracked/is new/untracked, git missing, etc.)."""
    root = repo_root_for(file)
    if root is None:
        return None
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "blame", "--porcelain", "-w", "--", file],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None

    # Porcelain format: each line's header is `<40-char sha> <orig-line>
    # <final-line> [num-lines-in-group]` — the trailing metadata (author,
    # author-time, summary, ...) only appears attached to a commit's FIRST
    # header line in this output, not on every repeat. Since blame emits
    # lines in final-file order, a commit's first occurrence always comes
    # before any repeat, so a single top-to-bottom pass caching author-time
    # per commit hash is enough — no second pass needed.
    lines: dict[int, LineBlame] = {}
    commit_times: dict[str, int] = {}
    pending_line: int | None = None
    pending_commit: str | None = None
    for raw in result.stdout.splitlines():
        if raw.startswith("\t"):
            pending_line = pending_commit = None
            continue
        parts = raw.split(" ")
        if len(parts) >= 3 and len(parts[0]) == 40 and all(c in "0123456789abcdef" for c in parts[0]):
            pending_commit, pending_line = parts[0], int(parts[2])
        elif raw.startswith("author-time ") and pending_commit is not None:
            commit_times[pending_commit] = int(raw.split(" ", 1)[1])
        if pending_commit is not None and pending_line is not None:
            lines[pending_line] = LineBlame(commit=pending_commit[:8], author_time=commit_times.get(pending_commit, 0))
    return lines or None


def node_git_info(
    file: str | None,
    lineno: int | None,
    end_lineno: int | None,
    blame_cache: dict[str, dict[int, LineBlame] | None],
) -> dict | None:
    """``{"last_change": unix_ts, "commit": short_hash, "churn": n_distinct_commits}``
    for the node spanning ``lineno..end_lineno`` in ``file``, or ``None``."""
    if not file or lineno is None:
        return None
    if file not in blame_cache:
        blame_cache[file] = blame_file(file)
    blame = blame_cache[file]
    if not blame:
        return None
    end = end_lineno or lineno
    in_range = [blame[ln] for ln in range(lineno, end + 1) if ln in blame]
    if not in_range:
        return None
    latest = max(in_range, key=lambda b: b.author_time)
    return {
        "last_change": latest.author_time,
        "commit": latest.commit,
        "churn": len({b.commit for b in in_range}),
    }


__all__ = ["node_git_info", "blame_file", "repo_root_for"]
