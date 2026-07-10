# Prompt dashboard (observability + optimization)

A Streamlit workbench to **understand and refine how your prompts talk to the LLM** — launch it
any time:

```bash
pip install "agentx-kit[dashboard]"
agentx dashboard                 # opens http://localhost:8501
agentx prompt set assistant -d   # edit a prompt AND open the dashboard
```

It gives you, live as you edit:

- **Token count, context-window utilization gauge, and cost estimate** (tiktoken-accurate).
- **Quality score (0–100)** with a checklist (role / goal / output-format / examples /
  constraints / specificity) and **concrete suggestions + limit warnings**.
- **✨ One-click LLM optimization** — refines the prompt while preserving intent, shows a
  **diff + rationale + token delta**, and can **apply the result straight back to
  `prompts.json`**.
- **▶️ Test run** — send the prompt to the model and see the response with **tokens in/out,
  latency, and cost**.
- **📈 Usage trends** — tokens, cost, and latency over time, logged locally to
  `.agentx/insights.jsonl`. The Trends tab also shows live cache hit-rate and $ saved when
  [response caching](caching.md) is enabled.

Run it inside a generated AgentX project and it reads/writes that project's `prompts.json`; run it
anywhere else for a free-form prompt scratchpad.

See [`agentx dashboard`](../cli/dashboard.md) for the CLI flags.
