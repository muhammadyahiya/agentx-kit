"""Deep agent demo — planning, filesystem, sub-agent delegation, reflection.

Needs a real LLM (this one makes actual model calls, unlike the other demos in
this folder). Set a provider's API key first, e.g.:

    export OPENAI_API_KEY=sk-...
    python examples/deep_agent_demo.py

Or point it at a local Ollama model (no key needed):

    python examples/deep_agent_demo.py --provider ollama --model llama3.2
"""
from __future__ import annotations

import argparse

from agentx.agents import DeepAgent, ReflectionConfig, SubAgentSpec


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", default="openai")
    parser.add_argument("--model", default="")
    parser.add_argument("--workspace", default="./workspace")
    parser.add_argument("--reflection", action="store_true", help="Add a critic/reflection revision loop.")
    args = parser.parse_args()

    agent = DeepAgent.create(
        goal=(
            "Research three notable open-source RAG frameworks and write a short "
            "comparison to comparison.md, then list the frameworks you compared "
            "in your final answer."
        ),
        provider=args.provider,
        model=args.model,
        workspace=args.workspace,
        subagents=[
            SubAgentSpec(
                name="researcher",
                description="Delegate open-ended web research questions to this sub-agent.",
                prompt="You are a meticulous web researcher. Cite your sources.",
            ),
        ],
        reflection=ReflectionConfig(enabled=args.reflection, max_revisions=2),
    )

    print(f"Deep agent starting (provider={args.provider}, reflection={args.reflection})...\n")
    result = agent.run()
    print(result)


if __name__ == "__main__":
    main()
