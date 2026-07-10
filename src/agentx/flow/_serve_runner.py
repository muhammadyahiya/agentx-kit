"""Subprocess entry point for ``agentx flow --serve``'s "Run" button.

Runs the target file exactly like ``agentx flow app.py --live`` does (same
``runpy.run_path`` call), but emits structured, sentinel-prefixed JSON trace
events on stdout as they happen — instead of just accumulating them
in-process — so the parent server process (:mod:`agentx.flow.server`) can
forward each one to the browser over SSE the instant it occurs.

    python -m agentx.flow._serve_runner <path>
"""
from __future__ import annotations

import json
import runpy
import sys
import time

from . import tracer

#: Prefixes a trace-event line so the parent process can tell it apart from
#: the target script's own ordinary stdout output (a NUL byte never appears
#: in normal text output, so this can't collide with real program output).
SENTINEL = "\x00AGENTX_TRACE\x00"


def _emit(event: dict) -> None:
    print(SENTINEL + json.dumps(event), flush=True)


def main(path: str) -> None:
    tracer.reset_trace()
    tracer.set_event_hook(_emit)
    try:
        runpy.run_path(path, run_name="__main__")
    except SystemExit:
        pass
    except Exception as exc:  # noqa: BLE001 — reported to the browser, not swallowed
        _emit({"type": "error", "message": str(exc), "ts": time.time()})
        raise


if __name__ == "__main__":
    main(sys.argv[1])
