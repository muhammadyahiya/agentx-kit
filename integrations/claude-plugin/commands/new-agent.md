---
description: Scaffold a complete AgentX-Kit agent project from a problem statement
argument-hint: <describe the agent / use case you want to build>
---
Build a complete, runnable agent project for this request using the AgentX-Kit MCP tools:

**$ARGUMENTS**

Steps:
1. Call `recommend_project` with the problem statement and briefly show the recommended stack (framework, provider, agents, features) + rationale.
2. Ask the user to confirm or adjust (provider/framework/enterprise), then call `create_agent_project` with the problem statement and any overrides.
3. Report the target directory, the generated file tree, and the exact run steps it returns. Offer to open key files (main.py, agents.py, prompts.json).

Keep it concise; the tools do the heavy lifting.
