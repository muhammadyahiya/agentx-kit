# Installation

Requires **Python 3.10–3.13** and, for the scaffolder's `.venv` creation,
[`uv`](https://docs.astral.sh/uv/).

## From PyPI (recommended)

```bash
pip install agentx-kit                 # core: CLI + scaffolder + base abstractions
pip install "agentx-kit[all]"          # everything
```

Each LLM provider is an **optional extra** so you only pull the SDKs you use:

```bash
pip install "agentx-kit[openai,langgraph]"        # OpenAI + LangGraph
pip install "agentx-kit[bedrock,crewai,rag,mcp]"  # Bedrock + CrewAI + RAG + MCP
```

## Using `uv`

```bash
uv pip install "agentx-kit[all]"
```

## From GitHub (latest, unreleased)

```bash
pip install "agentx-kit[all] @ git+https://github.com/muhammadyahiya/agentx-kit.git"
```

## From a local clone (development)

```bash
git clone https://github.com/muhammadyahiya/agentx-kit.git
cd agentx-kit
uv venv && uv pip install -e ".[all,dev]"   # or: pip install -e ".[all,dev]"
pytest -q
```

## Verify

```bash
agentx version
agentx providers     # lists every provider + the env vars it needs
```

## Installation extras

| Extra | Installs | For |
|---|---|---|
| `openai` / `azure` / `openrouter` | `langchain-openai` | OpenAI-compatible |
| `anthropic` | `langchain-anthropic` | Claude |
| `google` | `langchain-google-genai` | Gemini (AI Studio) |
| `vertex` | `langchain-google-vertexai` | Vertex AI |
| `bedrock` | `langchain-aws` | Amazon Bedrock |
| `groq` | `langchain-groq` | Groq |
| `ollama` | `langchain-ollama` | local |
| `langgraph` | `langgraph`, `langchain` | LangGraph agents |
| `crewai` | `crewai` | CrewAI crews |
| `rag` | `langchain-community`, `chromadb` | RAG |
| `mcp` | `langchain-mcp-adapters`, `mcp` | MCP client tools + built-in MCP server templates |
| `observability` | `opentelemetry-*`, `openinference-*` | tracing |
| `server` | `fastapi`, `uvicorn` | serving; also powers `agentx flow --serve` |
| `typecheck` | `ruff`, `ty` | `agentx flow --typecheck` |
| `voice` | `faster-whisper`, `edge-tts`, `pyttsx3` | Speech-to-Text + Text-to-Speech |
| `streamlit` | `streamlit` | Streamlit chat/voice UI |
| `dashboard` | `streamlit`, `tiktoken`, `pandas` | prompt observability dashboard |
| `connector` | `mcp` | MCP server for Claude/Copilot/Codex |
| `all` | everything above | kitchen sink |

See [DESIGN.md](https://github.com/muhammadyahiya/agentx-kit/blob/main/DESIGN.md) for the
architecture and [RESEARCH.md](https://github.com/muhammadyahiya/agentx-kit/blob/main/RESEARCH.md)
for the competitive analysis behind these features.
