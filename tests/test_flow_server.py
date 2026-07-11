"""Tests for agentx.flow.server — the `--serve` live-execution backend."""
from __future__ import annotations

import json
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


def test_index_serves_react_bundle_when_react_true(tmp_path: Path) -> None:
    p = _write(tmp_path, "def a():\n    pass\n")
    app = build_app(build_static_flow(p), p, react=True)
    client = TestClient(app)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "AGENTX_FLOW_DATA" in resp.text
    assert '"serve_token"' in resp.text


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


def test_default_run_reports_nonzero_exit_code_on_sys_exit(tmp_path: Path) -> None:
    # Regression test: _serve_runner used to swallow SystemExit entirely, so
    # a script calling sys.exit(1) still reported exit_code 0 to the browser.
    p = _write(tmp_path, """
import sys

if __name__ == "__main__":
    print("about to fail")
    sys.exit(1)
""")
    app = build_app(build_static_flow(p), p)
    client = TestClient(app)
    token = _token(client)

    run_id = client.post(f"/api/run?token={token}").json()["run_id"]
    with client.stream("GET", f"/api/stream/{run_id}?token={token}") as resp:
        events = [json.loads(line[len("data:"):].strip()) for line in resp.iter_lines() if line.startswith("data:")]

    assert any(e["type"] == "stdout" and "about to fail" in e["text"] for e in events)
    assert events[-1]["type"] == "done"
    assert events[-1]["exit_code"] == 1


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


def test_custom_command_runs_and_streams_stdout(tmp_path: Path) -> None:
    # The terminal box: an arbitrary command instead of the default target
    # file — plain subprocess streaming, no tracer/trace events involved.
    p = _write(tmp_path, "def a():\n    pass\n")
    app = build_app(build_static_flow(p), p)
    client = TestClient(app)
    token = _token(client)

    run_id = client.post(
        f"/api/run?token={token}", json={"command": "python3 -c \"print('from terminal')\""},
    ).json()["run_id"]
    with client.stream("GET", f"/api/stream/{run_id}?token={token}") as resp:
        events = [json.loads(line[len("data:"):].strip()) for line in resp.iter_lines() if line.startswith("data:")]

    assert not any(e["type"] in ("trace_call", "trace_return") for e in events)
    assert any(e["type"] == "stdout" and "from terminal" in e["text"] for e in events)
    assert events[-1] == {"type": "done", "exit_code": 0, "ts": events[-1]["ts"]}


def test_custom_command_bad_syntax_is_shell_error_not_a_500(tmp_path: Path) -> None:
    # Arbitrary commands run through a real shell (cross-platform quoting,
    # `&&`, pipes) — so malformed syntax is the *shell's* problem, surfaced as
    # normal stderr output and a nonzero exit code, not a Python-level 400/500.
    p = _write(tmp_path, "def a():\n    pass\n")
    app = build_app(build_static_flow(p), p)
    client = TestClient(app)
    token = _token(client)

    run_id = client.post(
        f"/api/run?token={token}", json={"command": 'python3 -c "unterminated'},
    ).json()["run_id"]
    with client.stream("GET", f"/api/stream/{run_id}?token={token}") as resp:
        assert resp.status_code == 200
        events = [json.loads(line[len("data:"):].strip()) for line in resp.iter_lines() if line.startswith("data:")]
    assert events[-1]["type"] == "done"
    assert events[-1]["exit_code"] != 0


def test_unknown_command_reports_not_found_without_crashing(tmp_path: Path) -> None:
    # The exact bug this fixes: a mistyped/missing command (e.g. "streamline"
    # instead of "streamlit") used to raise an uncaught FileNotFoundError,
    # crashing the whole ASGI request with a 500. It must now behave like a
    # real shell: print its own "not found" error and exit nonzero.
    p = _write(tmp_path, "def a():\n    pass\n")
    app = build_app(build_static_flow(p), p)
    client = TestClient(app)
    token = _token(client)

    resp = client.post(f"/api/run?token={token}", json={"command": "definitely_not_a_real_command_xyz"})
    assert resp.status_code == 200
    run_id = resp.json()["run_id"]
    with client.stream("GET", f"/api/stream/{run_id}?token={token}") as resp:
        events = [json.loads(line[len("data:"):].strip()) for line in resp.iter_lines() if line.startswith("data:")]
    assert events[-1]["type"] == "done"
    assert events[-1]["exit_code"] != 0


def test_terminal_python_command_for_package_file_resolves_relative_imports(tmp_path: Path) -> None:
    # "python main.py" typed into the terminal box, where main.py is part of
    # a package using relative imports, must not hit "attempted relative
    # import with no known parent package" — same fix as the default Run
    # button (execrun.run_target), applied transparently to typed commands too.
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "pkg" / "config.py").write_text("SETTING = 'hello'\n", encoding="utf-8")
    main_py = tmp_path / "pkg" / "main.py"
    main_py.write_text(
        "from .config import SETTING\n\nif __name__ == '__main__':\n    print('SETTING =', SETTING)\n",
        encoding="utf-8",
    )
    flow = build_static_flow(main_py)
    app = build_app(flow, main_py)
    client = TestClient(app)
    token = _token(client)

    import sys
    run_id = client.post(
        f"/api/run?token={token}", json={"command": f"{sys.executable} {main_py}"},
    ).json()["run_id"]
    with client.stream("GET", f"/api/stream/{run_id}?token={token}") as resp:
        events = [json.loads(line[len("data:"):].strip()) for line in resp.iter_lines() if line.startswith("data:")]

    assert not any(e["type"] == "error" for e in events)
    assert any(e["type"] == "stdout" and "SETTING = hello" in e["text"] for e in events)
    assert events[-1]["type"] == "done"
    assert events[-1]["exit_code"] == 0


def test_terminal_command_for_non_package_python_file_runs_unmodified(tmp_path: Path) -> None:
    # A `python script.py` command where script.py is NOT part of a package
    # should not be rewritten — it already runs fine as a literal command.
    p = _write(tmp_path, "def a():\n    pass\n")
    standalone = tmp_path / "standalone.py"
    standalone.write_text("print('standalone ran')\n", encoding="utf-8")
    app = build_app(build_static_flow(p), p)
    client = TestClient(app)
    token = _token(client)

    import sys
    run_id = client.post(
        f"/api/run?token={token}", json={"command": f"{sys.executable} {standalone}"},
    ).json()["run_id"]
    with client.stream("GET", f"/api/stream/{run_id}?token={token}") as resp:
        events = [json.loads(line[len("data:"):].strip()) for line in resp.iter_lines() if line.startswith("data:")]
    assert any(e["type"] == "stdout" and "standalone ran" in e["text"] for e in events)


def test_finished_runs_are_swept_after_retention_window(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Regression test: `runs` used to grow forever (a `_Run` — Popen + Queue —
    # per Run click, never removed). A run older than the retention window
    # must be pruned the next time a run starts.
    import time as time_mod

    import agentx.flow.server as server_mod

    monkeypatch.setattr(server_mod, "_RUN_RETENTION_SECONDS", 0)
    p = _write(tmp_path, "def a():\n    pass\n")
    app = build_app(build_static_flow(p), p)
    client = TestClient(app)
    token = _token(client)

    first_run_id = client.post(f"/api/run?token={token}").json()["run_id"]
    with client.stream("GET", f"/api/stream/{first_run_id}?token={token}") as resp:
        list(resp.iter_lines())  # drain to completion so `done`/finished_at are set

    assert first_run_id in app.state.runs
    time_mod.sleep(0.05)  # ensure now - finished_at > 0 (the monkeypatched retention window)

    second_run_id = client.post(f"/api/run?token={token}").json()["run_id"]
    with client.stream("GET", f"/api/stream/{second_run_id}?token={token}") as resp:
        list(resp.iter_lines())

    assert first_run_id not in app.state.runs
    assert second_run_id in app.state.runs


def test_custom_command_runs_in_invocation_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = _write(tmp_path, "def a():\n    pass\n")
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    monkeypatch.chdir(workdir)
    app = build_app(build_static_flow(p), p)  # build_app captures Path.cwd() at build time
    client = TestClient(app)
    token = _token(client)

    run_id = client.post(
        f"/api/run?token={token}", json={"command": "python3 -c \"import os; print(os.getcwd())\""},
    ).json()["run_id"]
    with client.stream("GET", f"/api/stream/{run_id}?token={token}") as resp:
        events = [json.loads(line[len("data:"):].strip()) for line in resp.iter_lines() if line.startswith("data:")]
    stdout_text = next(e["text"] for e in events if e["type"] == "stdout")
    assert Path(stdout_text).resolve() == workdir.resolve()
