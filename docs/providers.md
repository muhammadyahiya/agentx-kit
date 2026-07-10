# Providers

```bash
agentx providers
```

Lists every supported provider, its optional-install extra, default model, and required
environment variables:

| id | provider | extra | default model | env vars |
|---|---|---|---|---|
| `openai` | OpenAI | `openai` | `gpt-4o-mini` | `OPENAI_API_KEY` |
| `azure` | Azure OpenAI | `azure` | `gpt-4o` | `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT` |
| `openrouter` | OpenRouter | `openrouter` | `openai/gpt-4o-mini` | `OPENROUTER_API_KEY` |
| `anthropic` | Anthropic (Claude) | `anthropic` | `claude-sonnet-4-6` | `ANTHROPIC_API_KEY` |
| `gemini` | Google Gemini (AI Studio) | `google` | `gemini-1.5-flash` | `GOOGLE_API_KEY` |
| `vertexai` | Google Vertex AI | `vertex` | `gemini-1.5-flash` | `GOOGLE_CLOUD_PROJECT`, `GOOGLE_APPLICATION_CREDENTIALS` |
| `bedrock` | Amazon Bedrock | `bedrock` | `anthropic.claude-3-5-sonnet-20240620-v1:0` | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` |
| `groq` | Groq | `groq` | `llama-3.3-70b-versatile` | `GROQ_API_KEY` |
| `ollama` | Ollama (local) | `ollama` | `llama3.2` | — (local) |
| `huggingface` | HuggingFace | `huggingface` | `HuggingFaceH4/zephyr-7b-beta` | `HF_TOKEN` |
| `cohere` | Cohere | `cohere` | `command-r-plus` | `COHERE_API_KEY` |
| `mistral` | Mistral AI | `mistral` | `mistral-large-latest` | `MISTRAL_API_KEY` |

Install only what you use:

```bash
pip install "agentx-kit[openai,langgraph]"        # OpenAI + LangGraph
pip install "agentx-kit[bedrock,crewai,rag,mcp]"  # Bedrock + CrewAI + RAG + MCP
```

## Use as a library

```python
from agentx import get_chat_model, list_providers

llm = get_chat_model("openai", "gpt-4o-mini")
print(llm.invoke("Say hi in 3 words").content)

for spec in list_providers():
    print(spec.id, "→", spec.label)
```

CrewAI:

```python
from agentx import get_crewai_llm
llm = get_crewai_llm("openrouter", "anthropic/claude-3.5-sonnet")
```

One factory, every provider — `get_chat_model("bedrock", ...)` or
`get_chat_model("openrouter", ...)` is the same call with lazy imports; you only need the extra
installed for the provider you actually use.
