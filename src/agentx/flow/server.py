"""Local live-execution backend for ``agentx flow --serve``.

Unlike the default ``--ui`` (a static, offline HTML file — see
:mod:`agentx.flow.htmlgen`), clicking "Run" in the browser has to actually
execute code somewhere, so this mode trades that offline-file simplicity for
a small local FastAPI server: it serves the same viewer HTML plus three
endpoints that spawn a subprocess, stream its stdout/stderr (and, for the
default target-file run, structured trace events) to the browser over SSE,
and let the browser stop it.

The viewer's "Run" button, with no arguments, runs the target file via
:mod:`agentx.flow._serve_runner` (mirrors ``--live``'s execution path,
including full call/return trace events). The viewer's command box lets the
user instead type an arbitrary command (e.g. ``python main.py``) — that runs
as a plain subprocess (no tracer hook, since we don't control what it does),
still streamed live, effectively a minimal terminal for driving the project
from the graph view.

Import this module only after confirming ``fastapi``/``uvicorn``/
``sse_starlette`` are installed (the CLI does this with a guarded,
friendly-error import before ever reaching here) — it assumes they're
present.

Safety: every non-page route requires a random per-server ``token`` (see
:func:`build_app`) issued at startup and embedded in the served page, so
another localhost tab/process can't silently trigger execution. The server
itself must only ever be bound to ``127.0.0.1`` by its caller.
"""
from __future__ import annotations

import asyncio
import json
import queue
import secrets
import shlex
import subprocess
import sys
import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from sse_starlette.sse import EventSourceResponse

from ._serve_runner import SENTINEL
from .htmlgen import render_html
from .model import Flow


class _Run:
    def __init__(self, proc: subprocess.Popen) -> None:
        self.proc = proc
        self.queue: queue.Queue[dict] = queue.Queue()
        self.done = False


_PYTHON_EXE_NAMES = {"python", "python3", Path(sys.executable).name}


def _maybe_package_aware_rewrite(args: list[str], invocation_cwd: Path) -> list[str]:
    """If the terminal box's typed command is ``python <script>.py`` and that
    script turns out to be part of a package, route it through
    ``_serve_runner`` (== :func:`agentx.flow.execrun.run_target`) instead of
    running it as a literal subprocess — otherwise a perfectly reasonable
    ``python main.py`` would hit the exact "attempted relative import with no
    known parent package" failure the default Run button's execution path
    (``execrun.run_target``) already avoids. Also gains trace-event support
    for free. Any other command (not this exact shape) runs completely
    unmodified."""
    if len(args) < 2 or Path(args[0]).name not in _PYTHON_EXE_NAMES:
        return args
    script_arg = args[1]
    if script_arg.startswith("-") or not script_arg.endswith(".py"):
        return args
    script = Path(script_arg)
    if not script.is_absolute():
        script = invocation_cwd / script
    if not script.exists() or not (script.parent / "__init__.py").exists():
        return args
    return [sys.executable, "-m", "agentx.flow._serve_runner", str(script)]


def build_app(flow: Flow, target_path: str | Path, *, diagnostics: dict[str, list[dict]] | None = None) -> FastAPI:
    """Build the FastAPI app for ``agentx flow --serve``. Caller binds it to
    ``127.0.0.1`` via uvicorn; this function only wires routes."""
    token = secrets.token_urlsafe(16)
    target_path = str(target_path)
    invocation_cwd = Path.cwd()
    runs: dict[str, _Run] = {}
    app = FastAPI(title="agentx flow --serve", docs_url=None, redoc_url=None)

    def _check_token(request: Request) -> None:
        if request.query_params.get("token") != token:
            raise HTTPException(status_code=403, detail="missing or invalid token")

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return render_html(flow, diagnostics=diagnostics, serve=True, serve_token=token)

    @app.post("/api/run")
    async def start_run(request: Request) -> dict:
        _check_token(request)
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001 — empty/absent body is fine, just means "default run"
            body = {}
        command = (body or {}).get("command", "").strip()

        run_id = secrets.token_hex(8)
        if command:
            try:
                args = shlex.split(command)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=f"could not parse command: {exc}") from exc
            if not args:
                raise HTTPException(status_code=400, detail="empty command")
            args = _maybe_package_aware_rewrite(args, invocation_cwd)
        else:
            args = [sys.executable, "-m", "agentx.flow._serve_runner", target_path]

        proc = subprocess.Popen(
            args, cwd=invocation_cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1,
        )
        run = _Run(proc)
        runs[run_id] = run
        threading.Thread(target=_run_to_completion, args=(run,), daemon=True).start()
        return {"run_id": run_id}

    @app.post("/api/stop/{run_id}")
    def stop_run(run_id: str, request: Request) -> dict:
        _check_token(request)
        run = runs.get(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="unknown run_id")
        run.proc.terminate()
        return {"ok": True}

    @app.get("/api/stream/{run_id}")
    async def stream(run_id: str, request: Request):
        _check_token(request)
        run = runs.get(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="unknown run_id")

        async def generator():
            loop = asyncio.get_event_loop()
            while True:
                event = await loop.run_in_executor(None, run.queue.get)
                yield {"event": "message", "data": json.dumps(event)}
                if event.get("type") in ("done", "error"):
                    break

        return EventSourceResponse(generator())

    return app


def _pump(run: _Run, stream_name: str, pipe) -> None:
    for line in iter(pipe.readline, ""):
        line = line.rstrip("\n")
        if line.startswith(SENTINEL):
            try:
                event = json.loads(line[len(SENTINEL):])
            except json.JSONDecodeError:
                event = {"type": stream_name, "text": line, "ts": time.time()}
        else:
            event = {"type": stream_name, "text": line, "ts": time.time()}
        run.queue.put(event)
    pipe.close()


def _run_to_completion(run: _Run) -> None:
    """Drain stdout/stderr fully (join both pump threads) *before* enqueueing
    ``done`` — otherwise the browser could see "done" while log lines
    buffered in the pipe are still being read, out of order."""
    t_out = threading.Thread(target=_pump, args=(run, "stdout", run.proc.stdout), daemon=True)
    t_err = threading.Thread(target=_pump, args=(run, "stderr", run.proc.stderr), daemon=True)
    t_out.start()
    t_err.start()
    exit_code = run.proc.wait()
    t_out.join()
    t_err.join()
    run.queue.put({"type": "done", "exit_code": exit_code, "ts": time.time()})


__all__ = ["build_app"]
