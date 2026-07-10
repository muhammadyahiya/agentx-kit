# `agentx rag`

Manage a generated project's RAG knowledge base (upload docs, rebuild index).

```bash
agentx rag --help
```

| Subcommand | Purpose |
|---|---|
| `agentx rag upload` | Upload documents and (optionally) rebuild the index |
| `agentx rag build` | Rebuild the vector index from all files in `knowledge/` |
| `agentx rag list` | List documents in the knowledge base |

## `agentx rag upload`

Supports PDF, Excel (`.xlsx`/`.xls`), CSV, Word (`.docx`), TXT, and Markdown files. Documents are
copied to the project's `knowledge/` directory, then the RAG index is rebuilt with the configured
(or auto-detected) embedding provider.

| Flag | Description |
|---|---|
| `[files]...` | Files to upload (prompted interactively if omitted) |
| `-p, --project PATH` | Project root (auto-detected from cwd) |
| `--rebuild / --no-rebuild` | Rebuild the vector index after upload (default: rebuild) |
| `-s, --store TEXT` | `faiss` \| `chroma` \| `memory` (reads from `agentx.json` if blank) |
| `-e, --embedding TEXT` | Embedding provider override (e.g. `huggingface`, `openai`) |

### Examples

```bash
agentx rag upload report.pdf data.xlsx notes.md
agentx rag upload *.pdf --store faiss --embedding huggingface
agentx rag upload contract.pdf --no-rebuild   # add file only, rebuild later
agentx rag upload                             # prompts for a file path interactively
```

## `agentx rag build`

Rebuild the RAG vector index from all files already in `knowledge/`.

| Flag | Description |
|---|---|
| `-p, --project PATH` | Project root |
| `-s, --store TEXT` | `faiss` \| `chroma` \| `memory` |
| `-e, --embedding TEXT` | Embedding provider |

```bash
agentx rag build
agentx rag build -p ./my-bot --store chroma --embedding openai
```

## `agentx rag list`

```bash
agentx rag list
agentx rag list -p ./my-bot
```

Lists every document currently in the project's knowledge base.

## Incremental re-indexing

Uploads and builds use a manifest to avoid re-embedding unchanged files — running `agentx rag
build` repeatedly after adding just one new file only re-embeds what changed.
