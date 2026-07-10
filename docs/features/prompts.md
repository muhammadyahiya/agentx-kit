# Prompts: add at creation, or any time after

Prompts are **not baked into code** — every generated project keeps them in a `prompts.json` that
`agents.py` loads dynamically. Add an entry and the project runs it on next start, **no code
changes**.

```bash
# at creation
agentx new --yes -n chatops --prompt "You are a senior DevOps engineer. Be terse."

# after creation (run inside the project)
agentx prompt list
agentx prompt set assistant --text "You are an SRE. Prioritise reliability."
agentx prompt add reviewer --role "Code Reviewer" --goal "Review diffs" \
    --text "You review code for bugs and security."
agentx prompt remove reviewer
```

`prompts.json`:

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

See [`agentx prompt`](../cli/prompt.md) for the full flag reference and
[Prompt dashboard](dashboard.md) to tune prompts live with token/cost/quality feedback.
