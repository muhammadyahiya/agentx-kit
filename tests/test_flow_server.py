"""Tests for agentx.flow.server — the `--serve` live-execution backend."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("sse_starlette")

from fastapi.testclient import TestClient  # noqa: E402

from agentx.flow import build_static_flow  # noqa: E402
from agentx.flow.server import build_app  # noqa: E402


def _write(tmp_path: Path, source: str) -> Path:
    p = tmp_path / "app.py"
    p.write_text(source, encoding="utf-8")
    return p


def _token(client: TestClient) -> str:
    page = client.get("/").text
    m = re.search(r'"serve_token": "([^"]+)"', page)
    assert m, "serve_token not found in page"
    return m.group(1)


def test_index_serves_viewer_without_token(tmp_path: Path) -> None:
    p = _write(tmp_path, "def a():\n    pass\n")
    app = build_app(build_static_flow(p), p)
    client = TestClient(app)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "cytoscape" in resp.text


def test_run_without_token_is_rejected(tmp_path: Path) -> None:
    p = _write(tmp_path, "def a():\n    pass\n")
    app = build_app(build_static_flow(p), p)
    client = TestClient(app)
    assert client.post("/api/run").status_code == 403
    assert client.post("/api/run?token=wrong").status_code == 403


def test_run_and_stream_reports_stdout_and_trace_events(tmp_path: Path) -> None:
    p = _write(tmp_path, """
from agentx.flow import trace

@trace
def clean():
    print("cleaning")

@trace
def train():
    clean()
    print("done")

if __name__ == "__main__":
    train()
""")
    app = build_app(build_static_flow(p), p)
    client = TestClient(app)
    token = _token(client)

    run_id = client.post(f"/api/run?token={token}").json()["run_id"]
    with client.stream("GET", f"/api/stream/{run_id}?token={token}") as resp:
        assert resp.status_code == 200
        events = [line[len("data:"):].strip() for line in resp.iter_lines() if line.startswith("data:")]

    types = [__import__("json").loads(e)["type"] for e in events]
    assert "trace_call" in types
    assert "trace_return" in types
    assert "stdout" in types
    assert types[-1] == "done"


def test_stop_terminates_running_process(tmp_path: Path) -> None:
    p = _write(tmp_path, """
import time
for _ in range(100):
    time.sleep(0.2)
""")
    app = build_app(build_static_flow(p), p)
    client = TestClient(app)
    token = _token(client)

    run_id = client.post(f"/api/run?token={token}").json()["run_id"]
    stop_resp = client.post(f"/api/stop/{run_id}?token={token}")
    assert stop_resp.status_code == 200

    with client.stream("GET", f"/api/stream/{run_id}?token={token}") as resp:
        events = [line for line in resp.iter_lines() if line.startswith("data:")]
    last_event = __import__("json").loads(events[-1][len("data:"):].strip())
    assert last_event["type"] == "done"
    assert last_event["exit_code"] != 0


def test_stream_requires_token(tmp_path: Path) -> None:
    p = _write(tmp_path, "def a():\n    pass\n")
    app = build_app(build_static_flow(p), p)
    client = TestClient(app)
    token = _token(client)
    run_id = client.post(f"/api/run?token={token}").json()["run_id"]
    assert client.get(f"/api/stream/{run_id}").status_code == 403
