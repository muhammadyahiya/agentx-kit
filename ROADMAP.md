# AgentX-Kit — Bug Report & Roadmap

## Bugs found & fixed in 0.11.1

Ordered by severity. All items below are **fixed** in this release.

| # | Sev | Symptom | Root cause | Fix |
|---|-----|---------|------------|-----|
| 1 | **P0** | `import <pkg>.graph` (and `streamlit_app.py`) crashes with `ProviderError` / `ModuleNotFoundError` before you can run anything | Nodes built their ReAct agent, tools, sub-agents, RAG index and MCP sessions **eagerly at module import** | Lazy construction in `libs/agent_factory.py` and `agentx.swarm` — models/tools build on first invocation, cached; import is now cheap and side-effect free |
| 2 | **P0** | Sub-agents / MCP fail at runtime with `Cannot run the event loop while another loop is running` | `load_mcp_tools` and the sub-agent sync path called `asyncio.run` / `run_until_complete` while already inside the async graph loop (exposed once tool assembly became lazy) | Detect a running loop and offload the coroutine to a worker thread (`agentx.tools.mcp`, `agentx.swarm.subagent`) |
| 3 | **P1** | `prompts/` and `schemas/` folders were effectively empty (just a shared `__init__`) | No per-agent modules were generated | Generate `prompts/<agent>.py` (role/goal/guidelines → system + user prompt) and `schemas/<agent>.py` (typed Pydantic I/O with docstrings) for every agent |
| 4 | **P1** | Generated code felt "messy" | Logic concentrated in monolithic modules | Structured layout + shared `libs/agent_factory.py`; Pydantic models and docstrings throughout |
| 5 | **P2** | `agentx mcp` traceback; `agentx rag upload` "missing argument"; `run`/`research` undiscoverable; raw-JSON replies from llama3.2 | (fixed in 0.11.0) | preflight checks, interactive prompt, top-level aliases, tool-call coercion |

### Scenarios verified against local Ollama (llama3.2)
Single agent; supervisor / sequential / parallel (2 and 3 workers); + sub-agents;
+ RAG; + MCP; + voice; + Claw; + Streamlit; CrewAI. All generate, compile, and
run; the graph imports without any provider dependency installed.

## Roadmap — toward a best-in-class agentic kit

**Reliability & DX**
- [ ] Golden end-to-end test matrix in CI (generate → `uv sync` → smoke-run) per framework/feature combo, gated on a tiny local model.
- [ ] `agentx doctor` — diagnose env (provider keys, `uv`, Ollama, MCP `npx`) and print fixes.
- [ ] Structured-output mode wired by default (bind the generated `schemas/<agent>.py` via `with_structured_output`).

**Agent capabilities**
- [ ] First-class **human-in-the-loop** (LangGraph `interrupt`) + approval gates for tool calls.
- [ ] **Durable execution / persistence** backends (SQLite/Postgres checkpointer) as a scaffold option.
- [ ] Richer **swarm** topologies (hierarchical teams, shared scratchpad/blackboard, hand-off protocol).
- [ ] **Evaluation harness** upgrade: trajectory + tool-choice scoring, not just final-answer LLM-judge.

**Voice & channels**
- [ ] Streaming STT/TTS (partial transcripts, barge-in) for real-time voice.
- [ ] Real Claw channel adapters (WhatsApp/Telegram/Slack/email) with signature verification, behind the generic webhook.

**Observability & ops**
- [ ] Trace every node/tool span to OTel by default; ship a Grafana/Langfuse dashboard template.
- [ ] Token/cost budgets per session with graceful degradation.

**Ecosystem**
- [ ] Plugin API for third-party tools/providers/embedders.
- [ ] Template registry (`agentx new --from <template>`), e.g. `rag-chatbot`, `voice-assistant`, `research-crew`.
