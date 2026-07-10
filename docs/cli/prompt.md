# `agentx prompt`

Manage agent prompts **in a generated project** — edits `prompts.json`. Run these inside the
project directory (or pass `--project`).

```bash
agentx prompt --help
```

| Subcommand | Purpose |
|---|---|
| `agentx prompt list` | List agents and their (resolved) prompts |
| `agentx prompt set` | Set/replace an existing agent's system prompt |
| `agentx prompt add` | Add a new agent — picked up automatically on next run |
| `agentx prompt remove` | Remove an agent from the project |

## `agentx prompt list`

| Flag | Description |
|---|---|
| `--project PATH` | Project dir (default: search from cwd) |

```bash
agentx prompt list
```

## `agentx prompt set`

| Flag | Description |
|---|---|
| `AGENT` | Agent name to update (required) |
| `-t, --text TEXT` | New system prompt text |
| `-f, --file PATH` | Read prompt text from a file |
| `--project PATH` | Project dir |
| `-d, --dashboard` | Open the dashboard after saving |

```bash
agentx prompt set assistant --text "You are an SRE. Prioritise reliability."
agentx prompt set assistant --file ./new_prompt.txt
agentx prompt set assistant -t "Be terse." -d   # edit AND open the dashboard
```

## `agentx prompt add`

| Flag | Description |
|---|---|
| `AGENT` | New agent name (required) |
| `--role TEXT` | Agent role |
| `--goal TEXT` | Agent goal |
| `-t, --text TEXT` | System prompt (blank = auto-derived from role/goal) |
| `-f, --file PATH` | Read prompt text from a file |
| `--project PATH` | Project dir |
| `-d, --dashboard` | Open the dashboard after saving |

```bash
agentx prompt add reviewer --role "Code Reviewer" --goal "Review diffs" \
    --text "You review code for bugs and security."
```

## `agentx prompt remove`

| Flag | Description |
|---|---|
| `AGENT` | Agent name to remove (required) |
| `--project PATH` | Project dir |

```bash
agentx prompt remove reviewer
```

## How prompts work

Prompts are **not baked into code** — every generated project keeps them in `prompts.json`, which
`agents.py` loads dynamically. Add an entry and the project runs it on next start, no code
changes:

```json
{
  "with_rag": false,
  "agents": {
    "assistant": {"role": "...", "goal": "...", "system_prompt": "You are ..."}
  }
}
```

A blank `system_prompt` is auto-derived from the agent's role + goal. You can also just open
`prompts.json` in an editor — the CLI is a convenience, not a gate.
