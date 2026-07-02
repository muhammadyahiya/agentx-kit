"""Swarm / sub-agents for AgentX.

Compose hierarchical multi-agent systems with the *agent-as-tool* pattern: a
sub-agent is a full ReAct agent (own tools / MCP / web search) exposed to a
parent agent as a single callable tool.

    from agentx.swarm import make_subagent_tool
"""
from .subagent import SubAgentInput, make_subagent_tool

__all__ = ["make_subagent_tool", "SubAgentInput"]
