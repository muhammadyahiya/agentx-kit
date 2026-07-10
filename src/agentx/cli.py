"""AgentX command-line interface.

    agentx new          # interactive wizard → scaffold a project
    agentx providers    # list supported LLM providers + required env vars
    agentx version
"""
from __future__ import annotations

import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from . import __version__
from .providers import all_specs, get_spec
from .scaffold import AgentSpec, ProjectSpec, generate_project, run_wizard
from .scaffold import prompts_store

app = typer.Typer(
    add_completion=False,
    help="AgentX — provider-agnostic agentic framework + project scaffolder.",
    no_args_is_help=True,
)
console = Console()


@app.command()
def version() -> None:
    """Print the installed version."""
    console.print(f"agentx {__version__}")


@app.command()
def providers() -> None:
    """List supported LLM providers and the env vars each needs."""
    table = Table(title="Supported LLM providers", show_lines=False)
    table.add_column("id", style="cyan", no_wrap=True)
    table.add_column("provider")
    table.add_column("extra", style="green")
    table.add_column("default model")
    table.add_column("env vars", style="yellow")
    for s in all_specs():
        table.add_row(s.id, s.label, s.extra, s.default_model, ", ".join(s.env_vars) or "— (local)")
    console.print(table)


@app.command()
def dashboard(
    port: int = typer.Option(8501, "--port", help="Port for the dashboard server."),
    provider: str = typer.Option(None, "--provider", help="Default provider to preselect."),
    model: str = typer.Option(None, "--model", help="Default model to preselect."),
    project: Path = typer.Option(None, "--project", help="Project dir (default: cwd; auto-detects prompts.json)."),
) -> None:
    """Launch the prompt observability & optimization dashboard (Streamlit).

    A workbench to edit a prompt and see token usage, context-window utilization,
    cost, quality suggestions, one-click LLM optimization, and test runs — live.
    """
    from .dashboard import launch

    console.print(f"[cyan]Launching AgentX dashboard on http://localhost:{port} …[/] (Ctrl+C to stop)")
    try:
        launch(port=port, provider=provider, model=model, project=str(project) if project else None)
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1) from exc


cache_app = typer.Typer(help="Inspect/clear the local LLM response cache.", no_args_is_help=True)
app.add_typer(cache_app, name="cache")


@cache_app.command("stats")
def cache_stats_cmd(
    path: Path = typer.Option(".agentx/llm_cache.sqlite", "--path", help="Cache DB path."),
) -> None:
    """Show cache hit rate and estimated tokens/$ saved."""
    from .cache import cache_stats

    s = cache_stats(path)
    table = Table(title="LLM response cache")
    table.add_column("metric", style="cyan")
    table.add_column("value")
    for k in ("entries", "hits", "misses", "hit_rate", "tokens_saved", "est_usd_saved"):
        table.add_row(k, str(s[k]))
    console.print(table)
    console.print(f"[dim]{s['path']}[/]")


@cache_app.command("clear")
def cache_clear_cmd(
    path: Path = typer.Option(".agentx/llm_cache.sqlite", "--path", help="Cache DB path."),
) -> None:
    """Clear all cached responses and reset stats."""
    from .cache import clear_cache

    clear_cache(path)
    console.print("[green]✓[/] Cache cleared.")


@app.command()
def mcp(
    print_config: bool = typer.Option(False, "--print-config", help="Print MCP client config for Claude/Codex/Copilot and exit."),
) -> None:
    """Run AgentX-Kit as an MCP server (connector for Claude / Copilot / Codex).

    Once connected, a single prompt with a problem statement generates a complete
    project. Add it to a client with the config from `agentx mcp --print-config`.
    """
    if print_config:
        import json

        from .connector import client_config

        cfg = client_config()
        console.print("[bold]MCP client config[/] (Claude Desktop / Claude Code / Codex / Copilot):\n")
        console.print(json.dumps(cfg, indent=2))
        console.print("\n[bold]Claude Code one-liner:[/]")
        console.print("  claude mcp add agentx-kit -- agentx mcp")
        console.print("\n[dim]Add the JSON under \"mcpServers\" in your client's MCP config "
                      "(e.g. claude_desktop_config.json), then restart the client.[/]")
        return
    # Preflight: the MCP SDK is an optional extra. Fail with a clear, actionable
    # message instead of a traceback when it (or any connector dep) is missing.
    try:
        import mcp  # noqa: F401
    except ImportError:
        console.print(
            "[red]The MCP connector needs the MCP SDK.[/] Install it with:\n"
            "    uv pip install 'agentx-kit[connector]'\n"
            "    # or:  pip install 'agentx-kit[connector]'"
        )
        raise typer.Exit(1) from None

    # This is a stdio server driven by an MCP client (Claude/Copilot/Codex) — it
    # blocks waiting for the client to speak. Note that on stderr so running it
    # bare in a terminal isn't mistaken for a hang (stdout is the MCP channel).
    print(
        "agentx MCP server ready on stdio — waiting for an MCP client. "
        "This is not a hang; press Ctrl+C to stop. "
        "Add it to a client with `agentx mcp --print-config`.",
        file=sys.stderr,
        flush=True,
    )
    try:
        from .connector import run

        run()  # stdio; no stdout output (the client drives the protocol)
    except (RuntimeError, ImportError) as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1) from exc
    except KeyboardInterrupt:
        raise typer.Exit(0) from None


def _result_panel(result, spec: ProjectSpec) -> None:
    lines = [f"[bold green]✓[/] Project '{spec.slug}' created at:", f"  {result.target_dir}", ""]
    lines += [f"  • {m}" for m in result.messages]
    lines += [
        "",
        "[bold]Next steps:[/]",
        f"  cd {result.target_dir.name}",
        "  cp .env.example .env   # add your credentials",
        "  uv sync" if not result.synced else "  # deps already installed",
        f"  uv run {spec.slug}",
    ]
    if spec.use_mcp:
        lines += [
            "",
            f"[bold]MCP tools[/] ({', '.join(spec.effective_mcp_tools)}):",
            f"  uv run {spec.slug}-mcp-server         # run your own MCP server",
            f"  uv run python -m {spec.package}.mcp.client_demo   # sample client",
        ]
    console.print(Panel("\n".join(lines), title="AgentX", border_style="cyan"))


@app.command()
def graph(
    project: Path = typer.Option(None, "--project", "-p", help="Project dir (auto-detects agentx.json)."),
    fmt: str = typer.Option("ascii", "--format", "-f", help="ascii | mermaid | json"),
    introspect: bool = typer.Option(
        False, "--introspect",
        help="Import the compiled LangGraph for a ground-truth mermaid diagram (needs deps).",
    ),
) -> None:
    """Show the structure and agent flow of a generated project.

    Reads ``agentx.json`` and renders the agents, orchestration, tools, RAG/memory,
    and the node/edge flow. Works with zero project dependencies installed.

    Examples:

        agentx graph                      # pretty tree of the project in cwd
        agentx graph -f mermaid           # mermaid graph (paste into a .md / VS Code)
        agentx graph -f json              # machine-readable structure
        agentx graph --introspect -f mermaid   # real compiled-graph diagram
    """
    from .scaffold import graphviz

    try:
        root, manifest = graphviz.load_manifest(project)
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1) from exc

    flow = graphviz.build_flow(manifest)
    fmt = fmt.lower()
    if fmt == "json":
        import json as _json
        console.print_json(_json.dumps(graphviz.render_json(manifest, flow)))
    elif fmt == "mermaid":
        text = None
        if introspect:
            text = graphviz.introspect_mermaid(root, manifest)
            if text is None:
                console.print("[dim]# introspection unavailable; showing manifest-derived diagram[/]")
        console.print(text or graphviz.render_mermaid(manifest, flow), soft_wrap=True)
    else:
        # soft_wrap: this is a preformatted ASCII tree — Rich's default word-wrap
        # would reflow long lines mid-branch instead of just letting them extend
        # past the visible width like `tree`/`ls` output does.
        console.print(graphviz.render_ascii(manifest, flow), soft_wrap=True)


@app.command()
def flow(
    path: Path = typer.Argument(Path("."), help="Python file or directory to analyze (default: current directory)."),
    entry: str = typer.Option("", "--entry", "-e", help="Static mode: only the subgraph reachable from this function."),
    fmt: str = typer.Option("ascii", "--format", "-f", help="ascii | mermaid | json | dot"),
    external: bool = typer.Option(True, "--external/--no-external", help="Include calls to non-local functions (stdlib/3rd-party)."),
    live: bool = typer.Option(
        False, "--live",
        help="Execute the file and render the ACTUAL runtime call graph (needs @agentx.flow.trace decorators in the target file). Single file only.",
    ),
    ui: bool = typer.Option(False, "--ui", help="Open an interactive 2D/3D DAG viewer in your browser instead of printing text."),
    out: Path = typer.Option(None, "--out", "-o", help="With --ui, write the viewer HTML here instead of a temp file."),
    no_open: bool = typer.Option(False, "--no-open", help="With --ui, write the viewer file but don't launch a browser."),
    typecheck: bool = typer.Option(
        False, "--typecheck",
        help="Run mypy and attach type-check diagnostics to nodes (requires `agentx-kit[typecheck]`).",
    ),
    serve: bool = typer.Option(
        False, "--serve",
        help=(
            "Start a local live-execution server: click Run in the viewer to "
            "execute the file and stream logs (implies --ui; single file only; "
            "requires `agentx-kit[server]`)."
        ),
    ),
) -> None:
    """Show a Python file's — or a whole project's — function-call flow as a DAG.

    Static mode (default) parses the file (or every file under a directory)
    with `ast` — nothing is imported or executed. Live mode (`--live`, single
    file only) actually runs the file, so any `@agentx.flow.trace`-decorated
    functions are recorded with real call counts and timing. `--ui` renders
    an interactive 2D/3D graph viewer instead of text; `--typecheck` attaches
    mypy diagnostics to it; `--serve` (single file only) starts a local
    server so you can click Run in the viewer and watch it execute live.

    Examples:

        agentx flow                              # static call graph, whole project (cwd)
        agentx flow --ui                          # ...as an interactive 2D/3D viewer
        agentx flow --ui --typecheck              # ...with mypy diagnostics attached
        agentx flow app.py                        # static call graph, one file
        agentx flow app.py --entry train_model -f mermaid
        agentx flow app.py --live                 # run it, show the real execution graph
        agentx flow app.py --serve                # run it live from the browser, streamed logs
        agentx flow app.py -f dot > flow.dot && dot -Tsvg flow.dot -o flow.svg
    """
    from . import flow as flow_lib

    if not path.exists():
        console.print(f"[red]Path not found:[/] {path}")
        raise typer.Exit(1)

    if serve:
        if live:
            console.print("[red]--live and --serve are two different execution modes — pick one.[/]")
            raise typer.Exit(1)
        if path.is_dir():
            console.print("[red]--serve only supports a single file, not a directory.[/]")
            raise typer.Exit(1)
        if out:
            console.print("[red]--serve starts a live server rather than writing a file — --out isn't used with it.[/]")
            raise typer.Exit(1)
        ui = True

    if live:
        if path.is_dir():
            console.print("[red]--live only supports a single file, not a directory.[/]")
            raise typer.Exit(1)
        flow_lib.reset_trace()
        from .flow.execrun import run_target

        try:
            run_target(path)
        except SystemExit:
            pass
        except Exception as exc:  # noqa: BLE001
            console.print(f"[red]Error while running {path}:[/] {exc}")
            raise typer.Exit(1) from exc
        graph_result = flow_lib.get_current_flow()
        if not graph_result.nodes:
            console.print(
                "[yellow]No traced calls recorded.[/] Decorate functions with "
                "`@agentx.flow.trace` in the target file to see them here.\n"
            )
    else:
        try:
            if path.is_dir():
                graph_result = flow_lib.build_project_flow(path, entry=entry or None, include_external=external)
            else:
                graph_result = flow_lib.build_static_flow(path, entry=entry or None, include_external=external)
        except ValueError as exc:
            console.print(f"[red]{exc}[/]")
            raise typer.Exit(1) from exc

    diagnostics = None
    if typecheck:
        try:
            import mypy  # noqa: F401
        except ImportError:
            console.print("[red]--typecheck needs mypy.[/] Install it with:")
            console.print(
                "    uv pip install 'agentx-kit[typecheck]'\n"
                "    # or:  pip install 'agentx-kit[typecheck]'",
                markup=False,
            )
            raise typer.Exit(1) from None

        from .flow import typecheck as typecheck_lib

        with console.status("[bold]Type-checking with mypy...[/]"):
            file_diagnostics = typecheck_lib.run_mypy(path)
        diagnostics = typecheck_lib.map_diagnostics_to_nodes(graph_result, file_diagnostics)
        error_count = sum(1 for diags in diagnostics.values() for d in diags if d["severity"] == "error")
        console.print(f"[dim]mypy: {error_count} error{'s' if error_count != 1 else ''}[/]")

    if serve:
        try:
            import fastapi  # noqa: F401
            import sse_starlette  # noqa: F401
            import uvicorn
        except ImportError:
            console.print("[red]--serve needs the server extras.[/] Install them with:")
            console.print(
                "    uv pip install 'agentx-kit[server]'\n"
                "    # or:  pip install 'agentx-kit[server]'",
                markup=False,
            )
            raise typer.Exit(1) from None

        import socket
        import threading
        import time
        import webbrowser

        from .flow import server as server_lib

        def _free_port(preferred: int) -> int:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.bind(("127.0.0.1", preferred))
                    return preferred
                except OSError:
                    s.bind(("127.0.0.1", 0))
                    return s.getsockname()[1]

        port = _free_port(8765)
        url = f"http://127.0.0.1:{port}/"
        app_obj = server_lib.build_app(graph_result, path, diagnostics=diagnostics)
        console.print(f"[green]Serving at[/] {url}  [dim](binds to 127.0.0.1 only; Ctrl+C to stop)[/]")
        console.print("[yellow]Clicking Run in the viewer executes this file on your machine.[/]")
        if not no_open:
            def _open_when_ready() -> None:
                time.sleep(0.6)
                webbrowser.open(url)
            threading.Thread(target=_open_when_ready, daemon=True).start()
        uvicorn.run(app_obj, host="127.0.0.1", port=port, log_level="warning")
        return

    if ui:
        import tempfile
        import webbrowser

        html = flow_lib.render_html(graph_result, diagnostics=diagnostics)
        if out:
            out.write_text(html, encoding="utf-8")
            out_path = out
        else:
            with tempfile.NamedTemporaryFile(
                "w", suffix=".html", prefix="agentx-flow-", delete=False, encoding="utf-8",
            ) as fh:
                fh.write(html)
                out_path = Path(fh.name)
        console.print(f"[green]Wrote[/] {out_path}")
        if not no_open:
            webbrowser.open(out_path.resolve().as_uri())
        return

    fmt = fmt.lower()
    if fmt == "json":
        import json as _json
        console.print_json(_json.dumps(flow_lib.render_json(graph_result)))
    elif fmt == "mermaid":
        console.print(flow_lib.render_mermaid(graph_result), markup=False, soft_wrap=True)
    elif fmt == "dot":
        console.print(flow_lib.render_dot(graph_result), markup=False, soft_wrap=True)
    else:
        # soft_wrap: a real project's tree can have deeply-nested, long
        # module.Class.method names — Rich's default word-wrap would reflow
        # those lines mid-branch instead of letting them extend past the
        # visible terminal width like `tree`/`ls` output does.
        console.print(flow_lib.render_ascii(graph_result), markup=False, soft_wrap=True)


@app.command()
def new(
    name: str = typer.Option(None, "--name", "-n", help="Project name."),
    out: Path = typer.Option(None, "--out", "-o", help="Target directory (default ./<name>)."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Non-interactive: use defaults + options below."),
    framework: str = typer.Option("langgraph", help="langgraph | crewai (with --yes)."),
    provider: str = typer.Option("openai", help="Provider id (with --yes)."),
    model: str = typer.Option("", help="Model id (with --yes; blank = provider default)."),
    agents: int = typer.Option(1, help="Number of agents (with --yes)."),
    agent_mode: str = typer.Option("chat", "--agent-mode", help="chat|autonomous|research|deep (with --yes)."),
    deep_planning: bool = typer.Option(True, "--deep-planning/--no-deep-planning", help="Deep mode: write_todos planning tool (with --yes + --agent-mode deep)."),
    deep_filesystem: bool = typer.Option(True, "--deep-filesystem/--no-deep-filesystem", help="Deep mode: sandboxed filesystem tools (with --yes + --agent-mode deep)."),
    deep_reflection: bool = typer.Option(False, "--deep-reflection", help="Deep mode: critic/reflection revision loop (with --yes + --agent-mode deep)."),
    orchestration: str = typer.Option("supervisor", help="supervisor|sequential|parallel — how agents connect (with --yes, only for LangGraph with >1 agents)."),
    prompt: str = typer.Option("", "--prompt", "-p", help="System prompt for the first agent (with --yes)."),
    role: str = typer.Option("Helpful Assistant", help="Role for the first agent (with --yes)."),
    goal: str = typer.Option("Help the user accomplish their task accurately.", help="Goal for the first agent (with --yes)."),
    rag: bool = typer.Option(False, help="Include RAG (with --yes)."),
    domain: str = typer.Option("", "--domain", help="Domain seed: '' auto-infer, 'none' generic, or legal|medical|finance|support|devops|research."),
    problem: str = typer.Option("", "--problem", help="Problem statement — used to infer the domain."),
    memory: str = typer.Option("none", help="none|short|long|both (with --yes)."),
    mcp: bool = typer.Option(False, help="Include MCP tools (with --yes)."),
    mcp_tools: str = typer.Option(
        "", "--mcp-tools",
        help="Comma-separated subset of web_search,tts,knowledge_research,database for your own "
             "MCP server (with --yes + --mcp; blank = all four).",
    ),
    skills: bool = typer.Option(False, help="Include skills registry (with --yes)."),
    subagents: bool = typer.Option(False, help="Attach sub-agents/swarm (with --yes)."),
    voice: bool = typer.Option(False, help="Add voice I/O — STT + TTS (with --yes)."),
    streamlit: bool = typer.Option(False, help="Generate a Streamlit UI (with --yes)."),
    claw: bool = typer.Option(False, help="Add the Claw multi-channel assistant (with --yes)."),
    enterprise: bool = typer.Option(False, "--enterprise", help="Enable the full enterprise pack (tracing, guardrails, FastAPI, Docker, CI, evals)."),
    observability: bool = typer.Option(False, help="OpenTelemetry/Langfuse observability (with --yes)."),
    guardrails: bool = typer.Option(False, help="Input/output guardrails (with --yes)."),
    serve: bool = typer.Option(False, help="FastAPI server (REST + SSE) (with --yes)."),
    docker: bool = typer.Option(False, help="Dockerfile + docker-compose (with --yes)."),
    ci: bool = typer.Option(False, help="GitHub Actions CI (with --yes)."),
    evals: bool = typer.Option(False, help="LLM-as-judge eval harness (with --yes)."),
    no_venv: bool = typer.Option(False, "--no-venv", help="Do not create a .venv."),
    sync: bool = typer.Option(False, "--sync", help="Run `uv sync` after generating."),
    overwrite: bool = typer.Option(False, help="Overwrite a non-empty target directory."),
) -> None:
    """Scaffold a new agentic project (interactive by default)."""
    if yes:
        try:
            get_spec(provider)
        except KeyError as exc:
            raise typer.BadParameter(str(exc)) from exc
        agent_specs = []
        for i in range(max(1, agents)):
            a_name = f"agent_{i+1}" if agents > 1 else "assistant"
            # The --prompt/--role/--goal flags configure the first agent.
            if i == 0:
                agent_specs.append(AgentSpec(name=a_name, role=role, goal=goal, system_prompt=prompt))
            else:
                agent_specs.append(AgentSpec(name=a_name))
        spec = ProjectSpec(
            name=name or "my-agent", framework=framework, provider=provider, model=model,
            agents=agent_specs, orchestration=orchestration, agent_mode=agent_mode,
            deep_planning=deep_planning, deep_filesystem=deep_filesystem, deep_reflection=deep_reflection,
            use_rag=rag, memory=memory, use_mcp=mcp,
            mcp_tools=[t.strip() for t in mcp_tools.split(",") if t.strip()],
            use_skills=skills,
            use_subagents=subagents, use_voice=voice, streamlit=streamlit, claw=claw,
            domain=domain, problem_statement=problem,
            prompt_style="custom" if prompt else "default",
            observability=observability, guardrails=guardrails, serve=serve,
            docker=docker, ci=ci, evals=evals,
            create_venv=not no_venv, run_sync=sync,
        )
        if enterprise:
            spec.enable_enterprise()
    else:
        spec = run_wizard(name)
        if spec is None:
            console.print("[yellow]Cancelled.[/]")
            raise typer.Exit(1)
        if enterprise:
            spec.enable_enterprise()
        if no_venv:
            spec.create_venv = False
        if sync:
            spec.run_sync = True

    target = out or Path.cwd() / spec.slug
    try:
        result = generate_project(spec, target, overwrite=overwrite)
    except FileExistsError as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1) from exc
    _result_panel(result, spec)


# --------------------------------------------------------------------------- #
# `agentx prompt …` — manage prompts in an EXISTING generated project
# --------------------------------------------------------------------------- #
prompt_app = typer.Typer(help="Manage agent prompts in a generated project (edits prompts.json).", no_args_is_help=True)
app.add_typer(prompt_app, name="prompt")


def _resolve_prompts_file(project: Path | None) -> Path:
    path = prompts_store.find_prompts_file(project)
    if path is None:
        console.print(
            "[red]No prompts.json found.[/] Run this inside a AgentX project "
            "(or pass --project /path/to/project)."
        )
        raise typer.Exit(1)
    return path


def _read_text_arg(text: str | None, from_file: Path | None) -> str:
    if from_file:
        return Path(from_file).read_text(encoding="utf-8").strip()
    return (text or "").strip()


def _maybe_launch_dashboard(launch_flag: bool, project_dir: Path) -> None:
    """Open the prompt dashboard after an edit if requested."""
    if not launch_flag:
        console.print("  [dim]Tip: run `agentx dashboard` to tune this prompt live.[/]")
        return
    from .dashboard import launch

    console.print("[cyan]Opening dashboard…[/]")
    try:
        launch(project=str(project_dir))
    except RuntimeError as exc:
        console.print(f"[yellow]{exc}[/]")


@prompt_app.command("list")
def prompt_list(project: Path = typer.Option(None, "--project", help="Project dir (default: search from cwd).")) -> None:
    """List agents and their (resolved) prompts."""
    path = _resolve_prompts_file(project)
    data = prompts_store.load(path)
    table = Table(title=f"Agents in {path.parent.name}/prompts.json")
    table.add_column("agent", style="cyan")
    table.add_column("role")
    table.add_column("prompt", overflow="fold")
    for name, meta in data.get("agents", {}).items():
        sp = meta.get("system_prompt") or f"(auto from role/goal: {meta.get('goal','')})"
        table.add_row(name, meta.get("role", ""), sp)
    console.print(table)


@prompt_app.command("set")
def prompt_set(
    agent: str = typer.Argument(..., help="Agent name to update."),
    text: str = typer.Option("", "--text", "-t", help="New system prompt text."),
    from_file: Path = typer.Option(None, "--file", "-f", help="Read prompt text from a file."),
    project: Path = typer.Option(None, "--project"),
    dash: bool = typer.Option(False, "--dashboard", "-d", help="Open the dashboard after saving."),
) -> None:
    """Set/replace an existing agent's system prompt."""
    path = _resolve_prompts_file(project)
    body = _read_text_arg(text, from_file)
    if not body:
        body = typer.edit("\n# Enter the system prompt above this line.\n") or ""
        body = body.split("\n# Enter the system prompt")[0].strip()
    try:
        prompts_store.set_prompt(path, agent, body)
    except KeyError as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1) from exc
    console.print(f"[green]✓[/] Updated prompt for '{agent}'.")
    _maybe_launch_dashboard(dash, path.parent)


@prompt_app.command("add")
def prompt_add(
    agent: str = typer.Argument(..., help="New agent name."),
    role: str = typer.Option("", "--role"),
    goal: str = typer.Option("", "--goal"),
    text: str = typer.Option("", "--text", "-t", help="System prompt (blank = auto from role/goal)."),
    from_file: Path = typer.Option(None, "--file", "-f"),
    project: Path = typer.Option(None, "--project"),
    dash: bool = typer.Option(False, "--dashboard", "-d", help="Open the dashboard after saving."),
) -> None:
    """Add a new agent; the project picks it up automatically on next run."""
    path = _resolve_prompts_file(project)
    try:
        prompts_store.add_agent(path, agent, role=role, goal=goal, text=_read_text_arg(text, from_file))
    except KeyError as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1) from exc
    console.print(f"[green]✓[/] Added agent '{agent}'. It will run on next start — no code changes needed.")
    _maybe_launch_dashboard(dash, path.parent)


@prompt_app.command("remove")
def prompt_remove(
    agent: str = typer.Argument(..., help="Agent name to remove."),
    project: Path = typer.Option(None, "--project"),
) -> None:
    """Remove an agent from the project."""
    path = _resolve_prompts_file(project)
    try:
        prompts_store.remove_agent(path, agent)
    except (KeyError, ValueError) as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1) from exc
    console.print(f"[green]✓[/] Removed agent '{agent}'.")


# --------------------------------------------------------------------------- #
# `agentx rag …` — manage the RAG knowledge base of a generated project
# --------------------------------------------------------------------------- #
rag_app = typer.Typer(help="Manage the RAG knowledge base (upload docs, rebuild index).", no_args_is_help=True)
app.add_typer(rag_app, name="rag")


def _find_knowledge_dir(project: Path | None, *, create: bool = False) -> Path:
    """Resolve the knowledge/ directory for a generated agentx project.

    Args:
        project: Project root override (defaults to a walk-up search from cwd).
        create: When True, create the directory if missing.  Read-only commands
            (list/build) pass False so they don't leave empty ``knowledge/``
            folders behind.
    """
    base = project or Path.cwd()
    for parent in [base, *base.parents]:
        if (parent / "agentx.json").exists():
            kdir = parent / "knowledge"
            if create:
                kdir.mkdir(parents=True, exist_ok=True)
            return kdir
    kdir = base / "knowledge"
    if create:
        kdir.mkdir(parents=True, exist_ok=True)
    return kdir


@rag_app.command("upload")
def rag_upload(
    files: list[Path] = typer.Argument(None, help="Files to upload (PDF, Excel, CSV, Word, TXT, MD). Prompted if omitted."),
    project: Path = typer.Option(None, "--project", "-p", help="Project root (auto-detected from cwd)."),
    rebuild: bool = typer.Option(True, "--rebuild/--no-rebuild", help="Rebuild the vector index after upload."),
    vector_store: str = typer.Option("", "--store", "-s", help="faiss | chroma | memory (reads from agentx.json if blank)."),
    embedding_provider: str = typer.Option("", "--embedding", "-e", help="Embedding provider override (e.g. huggingface, openai)."),
) -> None:
    """Upload documents to the project knowledge base and (optionally) rebuild the index.

    Supports PDF, Excel (.xlsx/.xls), CSV, Word (.docx), TXT, and Markdown files.
    Documents are copied to the project's knowledge/ directory, then the RAG
    index is rebuilt with the configured (or auto-detected) embedding provider.

    Examples:

        agentx rag upload report.pdf data.xlsx notes.md

        agentx rag upload *.pdf --store faiss --embedding huggingface

        agentx rag upload contract.pdf --no-rebuild   # add file only, rebuild later

        agentx rag upload            # prompts for a file path interactively
    """
    import json as _json
    import shutil

    from .rag import RAGConfig, build_index_from_directory
    from .rag.embeddings import embedding_config_from_name

    # Interactive fallback: no files passed → prompt for one (or more, space-separated).
    if not files:
        console.print("[dim]No files given. Enter a path to a document to add to the knowledge base.[/]")
        answer = typer.prompt("File path(s) (space-separated, blank to cancel)", default="").strip()
        if not answer:
            console.print("[yellow]Nothing to upload.[/] "
                          "Run `agentx rag upload <file>` or `agentx rag build` to (re)index existing files.")
            raise typer.Exit(1)
        files = [Path(p).expanduser() for p in answer.split()]

    kdir = _find_knowledge_dir(project, create=True)
    console.print(f"[cyan]Knowledge directory:[/] {kdir}")

    # Copy files
    copied: list[Path] = []
    for fp in files:
        if not fp.exists():
            console.print(f"[yellow]Warning: file not found — {fp}[/]")
            continue
        dest = kdir / fp.name
        shutil.copy2(fp, dest)
        copied.append(dest)
        console.print(f"  [green]✓[/] {fp.name} → knowledge/{fp.name}")

    if not copied:
        console.print("[red]No files were copied.[/]")
        raise typer.Exit(1)

    console.print(f"\nCopied {len(copied)} file(s).")

    if not rebuild:
        console.print("[dim]Skipping index rebuild (--no-rebuild). Run `agentx rag build` to rebuild.[/]")
        return

    # Read project config for vector store / embedding
    proj_root = kdir.parent
    manifest_path = proj_root / "agentx.json"
    vs = vector_store
    ep = embedding_provider
    if manifest_path.exists():
        try:
            manifest = _json.loads(manifest_path.read_text())
            if not vs:
                vs = manifest.get("features", {}).get("vector_store") or "chroma"
            if not ep:
                ep = manifest.get("features", {}).get("embedding_provider") or ""
        except Exception:  # noqa: BLE001
            pass
    vs = vs or "chroma"
    persist = str(proj_root / f".{vs}")

    console.print(f"\n[cyan]Rebuilding index:[/] vector_store={vs} embedding={ep or 'auto'} …")

    try:
        emb_cfg = embedding_config_from_name(ep) if ep else None
        cfg = RAGConfig(vector_store=vs, persist_dir=persist)
        index = build_index_from_directory(kdir, config=cfg, embedding_config=emb_cfg)
        console.print(
            f"[green]✓[/] Index built: [bold]{len(index)} chunks[/] "
            f"in [bold]{index.store_type}[/] store → {persist}"
        )
    except Exception as exc:  # noqa: BLE001
        console.print(f"[yellow]Index build failed: {exc}[/]")
        console.print("[dim]The knowledge files were copied; rebuild manually once dependencies are installed.[/]")


@rag_app.command("build")
def rag_build(
    project: Path = typer.Option(None, "--project", "-p", help="Project root."),
    vector_store: str = typer.Option("", "--store", "-s", help="faiss | chroma | memory"),
    embedding_provider: str = typer.Option("", "--embedding", "-e", help="Embedding provider."),
) -> None:
    """Rebuild the RAG vector index from all files in knowledge/."""
    import json as _json

    from .rag import RAGConfig, build_index_from_directory
    from .rag.embeddings import embedding_config_from_name

    kdir = _find_knowledge_dir(project, create=False)
    if not kdir.exists():
        console.print(
            f"[red]No knowledge/ directory found[/] (looked in {kdir}). "
            "Run `agentx rag upload <file>` first."
        )
        raise typer.Exit(2)

    docs = [
        f for f in kdir.rglob("*")
        if f.is_file() and f.name != "README.md" and not f.name.startswith(".")
    ]
    if not docs:
        console.print(
            f"[yellow]No documents found in {kdir}.[/] "
            "Use `agentx rag upload <file>` to add PDF, Excel, CSV, Word, TXT, or MD files."
        )
        raise typer.Exit(2)

    proj_root = kdir.parent
    manifest_path = proj_root / "agentx.json"

    vs = vector_store
    ep = embedding_provider
    if manifest_path.exists():
        try:
            manifest = _json.loads(manifest_path.read_text())
            if not vs:
                vs = manifest.get("features", {}).get("vector_store") or "chroma"
            if not ep:
                ep = manifest.get("features", {}).get("embedding_provider") or ""
        except Exception:  # noqa: BLE001
            pass
    vs = vs or "chroma"
    persist = str(proj_root / f".{vs}")

    console.print(f"[cyan]Building RAG index:[/] store={vs} embedding={ep or 'auto'} docs={len(docs)} …")
    try:
        emb_cfg = embedding_config_from_name(ep) if ep else None
        cfg = RAGConfig(vector_store=vs, persist_dir=persist)
        index = build_index_from_directory(kdir, config=cfg, embedding_config=emb_cfg)
        if len(index) == 0:
            console.print("[red]Index built but empty — no chunks were produced from your documents.[/]")
            raise typer.Exit(3)
        console.print(
            f"[green]✓[/] {len(index)} chunks indexed in {index.store_type} → {persist}"
        )
    except typer.Exit:
        raise
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Build failed: {exc}[/]")
        raise typer.Exit(1) from exc


@rag_app.command("list")
def rag_list(
    project: Path = typer.Option(None, "--project", "-p", help="Project root."),
) -> None:
    """List documents in the knowledge base."""
    kdir = _find_knowledge_dir(project, create=False)
    if not kdir.exists():
        console.print(
            f"[yellow]No knowledge/ directory found[/] (looked in {kdir}). "
            "Use `agentx rag upload <file>` to add documents."
        )
        return
    files = [f for f in kdir.rglob("*") if f.is_file() and f.name != "README.md"]
    if not files:
        console.print("[yellow]knowledge/ is empty. Use `agentx rag upload <file>` to add documents.[/]")
        return
    table = Table(title=f"Knowledge base — {kdir}")
    table.add_column("file", style="cyan")
    table.add_column("type")
    table.add_column("size")
    for f in sorted(files):
        size = f.stat().st_size
        size_str = f"{size // 1024} KB" if size >= 1024 else f"{size} B"
        table.add_row(f.name, f.suffix.lstrip(".").upper() or "—", size_str)
    console.print(table)


# --------------------------------------------------------------------------- #
# `agentx agent …` — run autonomous / research agents
# --------------------------------------------------------------------------- #
agent_app = typer.Typer(help="Run autonomous and research agents.", no_args_is_help=True)
app.add_typer(agent_app, name="agent")


@agent_app.command("run")
def agent_run(
    goal: str = typer.Argument(..., help="Goal for the autonomous agent."),
    provider: str = typer.Option("openai", "--provider", "-p"),
    model: str = typer.Option("", "--model", "-m"),
    workspace: Path = typer.Option(Path("./workspace"), "--workspace", "-w"),
    max_iterations: int = typer.Option(20, "--max-iter"),
    allow_shell: bool = typer.Option(False, "--allow-shell", help="Allow shell command execution."),
) -> None:
    """Run an autonomous agent towards a goal.

    The agent plans, searches the web, reads/writes files, and works until it
    reaches the goal or hits the iteration cap.

    Example:

        agentx agent run "Research the top 5 RAG frameworks and write a report"
    """
    from .agents import AutonomousAgent

    console.print(f"[cyan]Autonomous agent:[/] {goal}")
    console.print(f"  provider={provider} workspace={workspace} max_iter={max_iterations}\n")

    agent = AutonomousAgent.create(
        goal=goal, provider=provider, model=model,
        workspace=str(workspace), max_iterations=max_iterations,
        allow_shell=allow_shell,
    )
    result = agent.run()
    if result.success:
        console.print(Panel(result.summary[:2000], title="[green]Agent Result[/]", border_style="green"))
        if result.artifacts:
            console.print(f"\nArtifacts ({len(result.artifacts)}):")
            for a in result.artifacts[:10]:
                console.print(f"  • {a}")
    else:
        console.print(f"[red]Agent failed:[/] {result.error}")
        raise typer.Exit(1)


@agent_app.command("research")
def agent_research(
    topic: str = typer.Argument(..., help="Research topic or question."),
    provider: str = typer.Option("openai", "--provider", "-p"),
    model: str = typer.Option("", "--model", "-m"),
    depth: str = typer.Option("standard", "--depth", "-d", help="quick | standard | deep"),
    output: Path = typer.Option(None, "--output", "-o", help="Save report to this file."),
) -> None:
    """Run a research agent to produce a sourced research report.

    Example:

        agentx agent research "LLM inference optimisation 2025" --depth deep -o report.md
    """
    from .agents import ResearchAgent

    console.print(f"[cyan]Research agent:[/] {topic} (depth={depth})")

    agent = ResearchAgent.create(
        topic=topic, provider=provider, model=model,
        depth=depth, output_file=str(output) if output else None,
    )
    result = agent.run()
    if result.success:
        console.print(Panel(
            result.markdown[:3000] + ("…" if len(result.markdown) > 3000 else ""),
            title="[green]Research Report[/]",
            border_style="green",
        ))
        console.print(
            f"\n[dim]Queries: {result.queries_run} | URLs: {result.urls_visited} | "
            f"Citations: {len(result.citations)}[/]"
        )
        if output:
            console.print(f"[green]✓[/] Report saved → {output}")
    else:
        console.print(f"[red]Research failed:[/] {result.error}")
        raise typer.Exit(1)


@agent_app.command("deep")
def agent_deep(
    goal: str = typer.Argument(..., help="Goal for the deep agent."),
    provider: str = typer.Option("openai", "--provider", "-p"),
    model: str = typer.Option("", "--model", "-m"),
    workspace: Path = typer.Option(Path("./workspace"), "--workspace", "-w"),
    max_iterations: int = typer.Option(25, "--max-iter"),
    planning: bool = typer.Option(True, "--planning/--no-planning", help="Give it a write_todos planning tool."),
    filesystem: bool = typer.Option(True, "--filesystem/--no-filesystem", help="Give it sandboxed file tools."),
    reflection: bool = typer.Option(False, "--reflection", help="Add a critic/reflection revision loop."),
    max_revisions: int = typer.Option(2, "--max-revisions"),
) -> None:
    """Run a deep agent: planning + filesystem + optional reflection loop.

    Example:

        agentx agent deep "Audit this repo's error handling and write a report."
    """
    from .agents import DeepAgent, ReflectionConfig

    console.print(f"[cyan]Deep agent:[/] {goal}")
    console.print(
        f"  provider={provider} workspace={workspace} planning={planning} "
        f"filesystem={filesystem} reflection={reflection}\n"
    )

    agent = DeepAgent.create(
        goal=goal, provider=provider, model=model,
        workspace=str(workspace), max_iterations=max_iterations,
        use_planning=planning, use_filesystem=filesystem,
        reflection=ReflectionConfig(enabled=reflection, max_revisions=max_revisions),
    )
    result = agent.run()
    if result.success:
        console.print(Panel(result.summary[:2000], title="[green]Deep Agent Result[/]", border_style="green"))
        if result.todos:
            console.print(f"\nFinal plan ({len(result.todos)} tasks):")
            for t in result.todos[:10]:
                console.print(f"  [{t.status}] {t.content}")
        if result.artifacts:
            console.print(f"\nArtifacts ({len(result.artifacts)}):")
            for a in result.artifacts[:10]:
                console.print(f"  • {a}")
        if result.revisions:
            console.print(f"\n[dim]Revisions: {result.revisions}[/]")
    else:
        console.print(f"[red]Deep agent failed:[/] {result.error}")
        raise typer.Exit(1)


# Top-level aliases for discoverability — `agentx research …` / `agentx run …` /
# `agentx deep …` mirror the `agentx agent …` subcommands (a common point of
# confusion).
app.command("research")(agent_research)
app.command("run")(agent_run)
app.command("deep")(agent_deep)


if __name__ == "__main__":
    app()
