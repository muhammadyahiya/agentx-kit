# `agentx cache`

Inspect/clear the local LLM response cache.

```bash
agentx cache --help
```

| Subcommand | Purpose |
|---|---|
| `agentx cache stats` | Show cache hit rate and estimated tokens/$ saved |
| `agentx cache clear` | Clear all cached responses and reset stats |

## Options (both subcommands)

| Flag | Description |
|---|---|
| `--path PATH` | Cache DB path (default `.agentx/llm_cache.sqlite`) |

## Examples

```bash
agentx cache stats
agentx cache clear
agentx cache stats --path ./my-bot/.agentx/llm_cache.sqlite
```

## Enable caching in your own code

```python
from agentx import enable_caching, cache_stats
enable_caching()                 # all get_chat_model(...) calls are cached
...
print(cache_stats())             # {'hit_rate': 0.6, 'tokens_saved': 12000, 'est_usd_saved': 0.024, ...}
```

SQLite-backed, TTL-capable, at `.agentx/llm_cache.sqlite`. See
[Response caching](../features/caching.md) for the full write-up.
