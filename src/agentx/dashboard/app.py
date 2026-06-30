"""AgentX — Prompt Observability & Optimization Dashboard (Streamlit).

Launched via ``agentx dashboard``. An observability workbench for understanding
and refining how your prompts interact with the LLM:

  • live token count, context-window utilization, and cost estimate
  • a heuristic quality score with concrete suggestions + limit warnings
  • one-click LLM optimization (refine while preserving intent) with a diff
  • a test run showing response, tokens in/out, latency, and cost
  • usage trends over time, logged locally to .agentx/insights.jsonl

If run inside a generated AgentX project, it reads/writes that project's
``prompts.json`` so optimizations can be applied in place.
"""
from __future__ import annotations

import difflib
import os
import time
from pathlib import Path

import streamlit as st

from agentx.insights import (
    analyze_prompt,
    count_tokens,
    estimate_cost,
    get_log,
    optimize_prompt,
    prompt_hash,
)
from agentx.insights.tokens import context_window
from agentx.providers import all_specs, get_spec

st.set_page_config(page_title="AgentX Prompt Dashboard", page_icon="🧬", layout="wide")

_PROJECT = Path(os.getenv("AGENTX_DASH_PROJECT", "."))
_DEFAULT_PROVIDER = os.getenv("AGENTX_DASH_PROVIDER", "openai")
_DEFAULT_MODEL = os.getenv("AGENTX_DASH_MODEL", "")


# --------------------------------------------------------------------------- #
# prompts.json integration (optional)
# --------------------------------------------------------------------------- #
def _load_prompts_store():
    try:
        from agentx.scaffold import prompts_store

        path = prompts_store.find_prompts_file(_PROJECT)
        if path:
            return prompts_store, path, prompts_store.load(path)
    except Exception:  # noqa: BLE001
        pass
    return None, None, None


def _log():
    return get_log(_PROJECT / ".agentx" / "insights.jsonl")


# --------------------------------------------------------------------------- #
# Sidebar — provider/model + prompt source
# --------------------------------------------------------------------------- #
def _sidebar():
    st.sidebar.header("🧬 AgentX Dashboard")
    specs = all_specs()
    ids = [s.id for s in specs]
    provider = st.sidebar.selectbox(
        "Provider", ids, index=ids.index(_DEFAULT_PROVIDER) if _DEFAULT_PROVIDER in ids else 0,
    )
    default_model = _DEFAULT_MODEL or get_spec(provider).default_model
    model = st.sidebar.text_input("Model", value=default_model)

    store, path, data = _load_prompts_store()
    source = "Free-form"
    agent_name = None
    initial_text = st.session_state.get("prompt_text", "")
    if store and data and data.get("agents"):
        st.sidebar.success(f"Project prompts: {path.parent.name}/prompts.json")
        choices = ["Free-form"] + list(data["agents"])
        source = st.sidebar.selectbox("Prompt source", choices)
        if source != "Free-form":
            agent_name = source
            meta = data["agents"][agent_name]
            loaded = meta.get("system_prompt") or ""
            if st.session_state.get("_loaded_agent") != agent_name:
                st.session_state["prompt_text"] = loaded
                st.session_state["_loaded_agent"] = agent_name
                initial_text = loaded
    else:
        st.sidebar.info("No prompts.json found — running in free-form mode. "
                        "Run inside an AgentX project to edit its prompts.")
    return provider, model, store, path, agent_name


# --------------------------------------------------------------------------- #
# Panels
# --------------------------------------------------------------------------- #
def _metrics_row(text: str, model: str):
    tokens = count_tokens(text, model)
    win = context_window(model)
    util = tokens / win if win else 0.0
    cost = estimate_cost(tokens, 0, model)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Tokens", f"{tokens:,}")
    c2.metric("Context window", f"{win:,}")
    c3.metric("Utilization", f"{util:.1%}")
    c4.metric("Est. input cost", f"${cost:.5f}")
    st.progress(min(1.0, util), text=f"Context window usage: {util:.1%}")
    return tokens


def _analysis_panel(text: str, model: str):
    a = analyze_prompt(text, model)
    score = a.quality_score
    color = "🟢" if score >= 75 else "🟡" if score >= 50 else "🔴"
    st.subheader(f"{color} Prompt quality: {score}/100")
    cols = st.columns(2)
    labels = {
        "has_role": "Role defined", "has_goal": "Goal stated",
        "has_output_format": "Output format", "has_examples": "Examples",
        "has_constraints": "Constraints", "not_vague": "Specific (not vague)",
        "reasonable_length": "Reasonable length",
    }
    items = list(a.checks.items())
    for i, (key, ok) in enumerate(items):
        cols[i % 2].markdown(f"{'✅' if ok else '⬜'} {labels.get(key, key)}")
    if a.suggestions:
        st.markdown("##### 💡 Suggestions")
        for s in a.suggestions:
            st.markdown(f"- {s}")
    for w in a.warnings:
        st.warning(w)


def _optimize_panel(text: str, provider: str, model: str, store, path, agent_name):
    st.subheader("✨ Optimize prompt")
    feedback = st.text_input("Optional feedback (tone, format, length, focus…)", key="opt_feedback")
    if st.button("Optimize with LLM", type="primary"):
        with st.spinner("Refining prompt (preserving intent)…"):
            result = optimize_prompt(text, provider, model, feedback=feedback)
        if not result.ok:
            st.error(f"Optimization failed: {result.error}")
        else:
            st.session_state["opt_result"] = {"improved": result.improved, "rationale": result.rationale}
            _log().record(kind="optimize", model=model, prompt_hash=prompt_hash(text),
                          tokens_in=count_tokens(text, model), tokens_out=count_tokens(result.improved, model),
                          note="prompt optimization")

    res = st.session_state.get("opt_result")
    if res:
        before = count_tokens(text, model)
        after = count_tokens(res["improved"], model)
        delta = after - before
        st.caption(f"Tokens: {before} → {after}  ({'+' if delta >= 0 else ''}{delta})")
        st.markdown("**Improved prompt**")
        st.code(res["improved"])
        if res["rationale"]:
            with st.expander("Why these changes?"):
                st.markdown(res["rationale"])
        with st.expander("Diff (original → improved)"):
            diff = difflib.unified_diff(
                text.splitlines(), res["improved"].splitlines(),
                fromfile="original", tofile="improved", lineterm="",
            )
            st.code("\n".join(diff) or "(no line-level changes)", language="diff")
        cols = st.columns(2)
        if cols[0].button("Use as current prompt"):
            st.session_state["prompt_text"] = res["improved"]
            st.session_state.pop("opt_result", None)
            st.rerun()
        if agent_name and store and path:
            if cols[1].button(f"💾 Apply to '{agent_name}' in prompts.json"):
                store.set_prompt(path, agent_name, res["improved"])
                st.session_state["prompt_text"] = res["improved"]
                st.session_state.pop("opt_result", None)
                st.success(f"Saved to prompts.json → {agent_name}. Your project picks it up on next run.")
                st.rerun()


def _run_panel(text: str, provider: str, model: str):
    st.subheader("▶️ Test run")
    user_msg = st.text_area("User message", value="Hello! Introduce yourself.", height=80, key="run_user")
    if st.button("Run against the model"):
        try:
            from agentx import get_chat_model
            from langchain_core.messages import HumanMessage, SystemMessage

            llm = get_chat_model(provider, model)
            messages = [SystemMessage(text), HumanMessage(user_msg)] if text.strip() else [HumanMessage(user_msg)]
            t0 = time.time()
            with st.spinner("Calling the model…"):
                resp = llm.invoke(messages)
            latency = int((time.time() - t0) * 1000)
            reply = getattr(resp, "content", str(resp))
            tin = count_tokens(text + user_msg, model)
            tout = count_tokens(reply, model)
            cost = estimate_cost(tin, tout, model)
            _log().record(kind="run", model=model, prompt_hash=prompt_hash(text),
                          tokens_in=tin, tokens_out=tout, cost_usd=cost, latency_ms=latency)
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Tokens in", f"{tin:,}")
            m2.metric("Tokens out", f"{tout:,}")
            m3.metric("Latency", f"{latency} ms")
            m4.metric("Est. cost", f"${cost:.5f}")
            st.markdown("**Response**")
            st.markdown(reply)
        except Exception as exc:  # noqa: BLE001
            st.error(f"Run failed: {exc}\n\nCheck your provider extra is installed and credentials are set.")


def _trends_panel():
    st.subheader("📊 Usage & trends")
    log = _log()
    agg = log.aggregate()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Runs", agg["runs"])
    c2.metric("Total tokens", f"{agg['total_tokens']:,}")
    c3.metric("Total cost", f"${agg['total_cost_usd']:.4f}")
    c4.metric("Avg latency", f"{agg['avg_latency_ms']} ms")

    # Response-cache savings (if caching has been used in this project).
    cache_path = _PROJECT / ".agentx" / "llm_cache.sqlite"
    if cache_path.exists():
        try:
            from agentx.cache import cache_stats

            cs = cache_stats(cache_path)
            st.markdown("###### 💾 Response cache")
            d1, d2, d3 = st.columns(3)
            d1.metric("Hit rate", f"{cs['hit_rate']:.0%}", help=f"{cs['hits']} hits / {cs['misses']} misses")
            d2.metric("Tokens saved", f"{cs['tokens_saved']:,}")
            d3.metric("Est. $ saved", f"${cs['est_usd_saved']:.4f}")
        except Exception:  # noqa: BLE001
            pass
    rows = [r for r in log.events() if r.get("kind") == "run"]
    if not rows:
        st.info("No runs logged yet — use **Test run** to populate trends.")
        return
    try:
        import pandas as pd

        df = pd.DataFrame(rows)
        df["ts"] = pd.to_datetime(df["ts"])
        df = df.set_index("ts")
        st.markdown("###### Tokens per run")
        st.line_chart(df[["tokens_in", "tokens_out"]], height=200)
        st.markdown("###### Cost (USD) per run")
        st.line_chart(df[["cost_usd"]], height=160)
        st.markdown("###### Latency (ms) per run")
        st.line_chart(df[["latency_ms"]], height=160)
    except Exception:  # noqa: BLE001 - pandas optional
        st.write(rows[-20:])


# --------------------------------------------------------------------------- #
def main():
    provider, model, store, path, agent_name = _sidebar()

    st.title("🧬 Prompt Observability & Optimization")
    st.caption("Edit a prompt, see token/cost/limits live, get suggestions, optimize, and test — all in one place.")

    text = st.text_area(
        "System prompt", value=st.session_state.get("prompt_text", ""),
        height=240, key="prompt_text",
        placeholder="You are a helpful assistant. Your goal is to…",
    )

    _metrics_row(text, model)
    st.divider()

    tab_analyze, tab_optimize, tab_run, tab_trends = st.tabs(
        ["🔎 Analysis", "✨ Optimize", "▶️ Test run", "📊 Trends"]
    )
    with tab_analyze:
        _analysis_panel(text, model)
    with tab_optimize:
        _optimize_panel(text, provider, model, store, path, agent_name)
    with tab_run:
        _run_panel(text, provider, model)
    with tab_trends:
        _trends_panel()


main()
