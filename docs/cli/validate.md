# `agentx validate`

Validate a generated project's `agentx.json` for structural correctness.

```bash
agentx validate
```

Checks required fields, that `framework`/`provider`/`agent_mode`/`orchestration`/`memory` are
recognized values, that `mcp_tools` are known tool names, and cross-checks against sibling files
(`pyproject.toml`, `prompts.json`, `.env.example`) for a few common drifts. Exits `1` if any
error-level finding is present (warnings alone still exit `0`).

## Options

| Flag | Description |
|---|---|
| `-p, --project PATH` | Project dir (auto-detects `agentx.json`) |

## Examples

```bash
agentx validate                  # validate the project in cwd
agentx validate -p ./my-bot      # validate a specific project
agentx validate && echo "ok"     # use the exit code in a script/CI step
```

Typical findings: an `agentx.json` referencing a provider extra that isn't installed, a prompt in
`prompts.json` with no matching agent, or a feature flag that's inconsistent with the generated
`pyproject.toml` dependencies (e.g. RAG enabled but `langchain-community` missing).
