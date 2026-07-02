"""Interaction log — append prompt edits/runs/optimizations for the dashboard.

A local JSONL at ``.agentx/insights.jsonl`` (project-local). Powers the usage
and trend charts: tokens in/out, cost, latency, model, per event.
"""
from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

_lock = threading.Lock()


def prompt_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:10]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class InsightEvent:
    ts: str = field(default_factory=_now)
    kind: str = "run"                  # run | edit | optimize | eval
    model: str = ""
    prompt_hash: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    note: str = ""
    # Optional interaction history (truncated). Defaults keep older JSONL lines valid.
    prompt_text: str = ""
    user_msg: str = ""
    response: str = ""
    eval_score: float = 0.0            # 0-1 relevance when a judge ran, else 0


class InsightLog:
    def __init__(self, path: str | Path = ".agentx/insights.jsonl"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def add(self, event: InsightEvent) -> InsightEvent:
        with _lock:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(asdict(event)) + "\n")
        return event

    def record(self, **kwargs) -> InsightEvent:
        return self.add(InsightEvent(**kwargs))

    def events(self, limit: int | None = None) -> list[dict]:
        if not self.path.exists():
            return []
        rows = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return rows[-limit:] if limit else rows

    def aggregate(self) -> dict:
        rows = self.events()
        runs = [r for r in rows if r.get("kind") == "run"]
        total_tokens = sum(r.get("tokens_in", 0) + r.get("tokens_out", 0) for r in runs)
        total_cost = round(sum(r.get("cost_usd", 0.0) for r in runs), 6)
        lat = [r.get("latency_ms", 0) for r in runs if r.get("latency_ms")]
        return {
            "events": len(rows),
            "runs": len(runs),
            "total_tokens": total_tokens,
            "total_cost_usd": total_cost,
            "avg_latency_ms": round(sum(lat) / len(lat)) if lat else 0,
            "optimizations": sum(1 for r in rows if r.get("kind") == "optimize"),
        }

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()


def get_log(path: str | Path = ".agentx/insights.jsonl") -> InsightLog:
    return InsightLog(path)
