"""Prompt insights: token/cost analysis, quality heuristics, LLM optimization, logging."""
from .analyze import PromptAnalysis, analyze_prompt
from .log import InsightEvent, InsightLog, get_log, prompt_hash
from .optimize import OptimizationResult, optimize_prompt
from .tokens import (
    TokenReport,
    context_window,
    count_tokens,
    estimate_cost,
    utilization,
)

__all__ = [
    "analyze_prompt", "PromptAnalysis",
    "optimize_prompt", "OptimizationResult",
    "count_tokens", "estimate_cost", "context_window", "utilization", "TokenReport",
    "InsightLog", "InsightEvent", "get_log", "prompt_hash",
]
