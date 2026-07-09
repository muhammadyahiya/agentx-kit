"""Flow demo — see this file's own function-call graph two ways: a static AST
call graph (no execution) and the actual runtime call graph (via @trace).

No API keys, no dependencies beyond agentx-kit itself.

    python examples/flow_demo.py                        # prints both graphs
    agentx flow examples/flow_demo.py --entry preprocess  # static graph, via the CLI
"""
from __future__ import annotations

from agentx.flow import build_static_flow, get_current_flow, render_ascii, trace


@trace
def load_csv() -> str:
    return "raw,csv,data"


@trace
def clean_data(data: str) -> str:
    return data.strip()


@trace
def validate(data: str) -> bool:
    return bool(data)


@trace
def preprocess() -> str:
    data = load_csv()
    data = clean_data(data)
    validate(data)
    return data


def main() -> None:
    preprocess()

    print("=== Static call graph (AST — no execution) ===")
    print(render_ascii(build_static_flow(__file__, entry="preprocess")))

    print("\n=== Runtime call graph (this run's actual calls + timing) ===")
    print(render_ascii(get_current_flow()))


if __name__ == "__main__":
    main()
