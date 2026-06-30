"""The AgentX prompt-observability dashboard (Streamlit)."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

APP = Path(__file__).parent / "app.py"


def launch(port: int = 8501, provider: str | None = None, model: str | None = None,
           project: str | None = None, headless: bool = False) -> int:
    """Launch the Streamlit dashboard. Raises a helpful error if Streamlit is absent."""
    try:
        import streamlit  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "The dashboard needs Streamlit. Install it with:\n"
            "    pip install 'agentx-kit[dashboard]'"
        ) from exc

    env = os.environ.copy()
    if provider:
        env["AGENTX_DASH_PROVIDER"] = provider
    if model:
        env["AGENTX_DASH_MODEL"] = model
    env["AGENTX_DASH_PROJECT"] = str(project or Path.cwd())

    cmd = [
        sys.executable, "-m", "streamlit", "run", str(APP),
        "--server.port", str(port),
        "--browser.gatherUsageStats", "false",
    ]
    if headless:
        cmd += ["--server.headless", "true"]
    return subprocess.run(cmd, env=env).returncode


__all__ = ["launch", "APP"]
