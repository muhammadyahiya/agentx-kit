"""AgentX command-line interface.

    agentx new          # interactive wizard → scaffold a project
    agentx providers    # list supported LLM providers + required env vars
    agentx version
"""
from __future__ import annotations

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
    try:
        from .connector import run
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1) from exc
    run()  # stdio; no console output (the client drives it)


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
    console.print(Panel("\n".join(lines), title="AgentX", border_style="cyan"))


@app.command()
def new(
    name: str = typer.Option(None, "--name", "-n", help="Project name."),
    out: Path = typer.Option(None, "--out", "-o", help="Target directory (default ./<name>)."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Non-interactive: use defaults + options below."),
    framework: str = typer.Option("langgraph", help="langgraph | crewai (with --yes)."),
    provider: str = typer.Option("openai", help="Provider id (with --yes)."),
    model: str = typer.Option("", help="Model id (with --yes; blank = provider default)."),
    agents: int = typer.Option(1, help="Number of agents (with --yes)."),
    prompt: str = typer.Option("", "--prompt", "-p", help="System prompt for the first agent (with --yes)."),
    role: str = typer.Option("Helpful Assistant", help="Role for the first agent (with --yes)."),
    goal: str = typer.Option("Help the user accomplish their task accurately.", help="Goal for the first agent (with --yes)."),
    rag: bool = typer.Option(False, help="Include RAG (with --yes)."),
    memory: str = typer.Option("none", help="none|short|long|both (with --yes)."),
    mcp: bool = typer.Option(False, help="Include MCP tools (with --yes)."),
    skills: bool = typer.Option(False, help="Include skills registry (with --yes)."),
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
            agents=agent_specs, use_rag=rag, memory=memory, use_mcp=mcp, use_skills=skills,
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


if __name__ == "__main__":
    app()
