# `agentx upgrade`

Re-run the **current** agentx-kit's templates over an existing project and show what changed.

```bash
agentx upgrade
```

Rebuilds the project spec from `agentx.json` (+ `prompts.json` for each agent's role/goal/prompt),
regenerates every templated file with the installed agentx-kit version's templates, and diffs it
against your live project. **Dry-run by default** — pass `--apply` to write. Useful after
upgrading agentx-kit to pick up template fixes/improvements in an already-generated project.

## Options

| Flag | Description |
|---|---|
| `-p, --project PATH` | Project dir (auto-detects `agentx.json`) |
| `--apply` | Write the changes (default: dry-run, only shows the plan) |
| `--force` | With `--apply`, also overwrite `prompts.json`/`knowledge`/`data` — normally left alone since they're meant to be hand/CLI-edited, not regenerated |

## Examples

```bash
agentx upgrade                    # dry-run: show what would change
agentx upgrade --apply            # write the regenerated template files
agentx upgrade -p ./my-bot --apply
agentx upgrade --apply --force    # also overwrite prompts.json / knowledge / data
```

!!! tip
    Run this after `pip install -U agentx-kit` to pull template fixes into a project you already
    generated, without losing your hand-edited prompts (unless you pass `--force`).
