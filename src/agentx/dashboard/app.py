"""AgentX — Prompt Observability, Optimization & Evaluation Dashboard (Streamlit).

Launched via ``agentx dashboard``. A workbench for understanding and refining how
prompts interact with the LLM:

  • provider + model picker for ALL providers (curated model catalog + free-text)
  • in-UI API-key entry per provider (session env, optional .env write)
  • live token count, context-window utilization, cost estimate
  • heuristic quality score + suggestions + one-click LLM optimization (with diff)
  • test runs with optional response caching
  • prompt/interaction history (persisted to .agentx/insights.jsonl)
  • evaluation metrics: relevance (LLM-judge), latency, cost, token efficiency, cache hit
  • usage trends over time

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
    evaluate_run,
    get_log,
    optimize_prompt,
    prompt_hash,
)
from agentx.insights.tokens import context_window
from agentx.providers import all_specs, get_spec
from agentx.providers.base import warn_missing_env
from agentx.providers.catalog import models_for

st.set_page_config(page_title="AgentX Prompt Dashboard", page_icon="🧬", layout="wide")

_PROJECT = Path(os.getenv("AGENTX_DASH_PROJECT", "."))
_DEFAULT_PROVIDER = os.getenv("AGENTX_DASH_PROVIDER", "openai")
_DEFAULT_MODEL = os.getenv("AGENTX_DASH_MODEL", "")
_CACHE_PATH = _PROJECT / ".agentx" / "llm_cache.sqlite"


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


def _write_env(path: Path, mapping: dict[str, str]) -> None:
    """Upsert KEY=value lines into a .env file without clobbering unrelated keys."""
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, _, v = line.partition("=")
                existing[k.strip()] = v
    existing.update({k: v for k, v in mapping.items() if v})
    body = "\n".join(f"{k}={v}" for k, v in existing.items()) + "\n"
    path.write_text(body, encoding="utf-8")


# --------------------------------------------------------------------------- #
# Sidebar — provider/model + credentials + prompt source
# --------------------------------------------------------------------------- #
def _credentials_panel(provider: str) -> None:
    """API-key entry for the selected provider — writes to the session env."""
    spec = get_spec(provider)
    missing = warn_missing_env(spec)
    label = "🔑 Credentials" + (" ⚠️" if missing else " ✅")
    with st.sidebar.expander(label, expanded=bool(missing and spec.env_vars)):
        if not spec.env_vars:
            st.caption(spec.notes or "No API key required (local provider).")
            return
        for var in spec.env_vars:
            val = st.text_input(var, value=os.getenv(var, ""), type="password", key=f"cred_{var}")
            if val:
                os.environ[var] = val
        if spec.notes:
            st.caption(spec.notes)
        if st.checkbox("Also save to project .env", key=f"persist_{provider}"):
            if st.button("💾 Write .env", key=f"writeenv_{provider}"):
                _write_env(_PROJECT / ".env", {v: os.environ.get(v, "") for v in spec.env_vars})
                st.success(f"Wrote {', '.join(spec.env_vars)} to {_PROJECT / '.env'}")


def _sidebar():
    st.sidebar.header("🧬 AgentX Dashboard")
    specs = all_specs()
    ids = [s.id for s in specs]
    labels = {s.id: s.label for s in specs}
    provider = st.sidebar.selectbox(
        "Provider", ids,
        index=ids.index(_DEFAULT_PROVIDER) if _DEFAULT_PROVIDER in ids else 0,
        format_func=lambda i: labels.get(i, i),
    )

    # Model: curated dropdown + free-text escape hatch (HF repos, Ollama tags, Azure deployments).
    default_model = _DEFAULT_MODEL or get_spec(provider).default_model
    opts = models_for(provider)
    if default_model and default_model not in opts:
        opts = [default_model] + opts
    picked = st.sidebar.selectbox(
        "Model", opts, index=opts.index(default_model) if default_model in opts else 0,
    )
    custom = st.sidebar.text_input("…or custom model id", value="", placeholder="override")
    model = custom.strip() or picked

    _credentials_panel(provider)

    store, path, data = _load_prompts_store()
    agent_name = None
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
    else:
        st.sidebar.info("No prompts.json found — free-form mode. "
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
    for i, (key, ok) in enumerate(a.checks.items()):
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
                st.success(f"Saved to prompts.json → {agent_name}. Picked up on next run.")
                st.rerun()


def _run_panel(text: str, provider: str, model: str):
    st.subheader("▶️ Test run")
    user_msg = st.text_area("User message", value="Hello! Introduce yourself.", height=80, key="run_user")
    c1, c2 = st.columns(2)
    use_cache = c1.checkbox("Use response cache", value=True, key="use_cache")
    do_eval = c2.checkbox("Score relevance (LLM judge)", value=False, key="do_eval")
    criteria = st.text_input("Success criteria (for scoring)", key="eval_criteria") if do_eval else ""

    if st.button("Run against the model"):
        try:
            from agentx import get_chat_model
            from langchain_core.messages import HumanMessage, SystemMessage

            if use_cache:
                from agentx.cache import enable_caching
                enable_caching(_CACHE_PATH)

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

            eval_score = 0.0
            if do_eval:
                with st.spinner("Judging relevance…"):
                    m = evaluate_run(text, user_msg, reply, provider=provider, model=model,
                                     latency_ms=latency, criteria=criteria)
                eval_score = m.relevance

            _log().record(
                kind="run", model=model, prompt_hash=prompt_hash(text),
                tokens_in=tin, tokens_out=tout, cost_usd=cost, latency_ms=latency,
                prompt_text=text[:2000], user_msg=user_msg[:2000], response=str(reply)[:2000],
                eval_score=eval_score,
            )
            cols = st.columns(5)
            cols[0].metric("Tokens in", f"{tin:,}")
            cols[1].metric("Tokens out", f"{tout:,}")
            cols[2].metric("Latency", f"{latency} ms")
            cols[3].metric("Est. cost", f"${cost:.5f}")
            if do_eval:
                cols[4].metric("Relevance", f"{eval_score:.1f}")
            st.markdown("**Response**")
            st.markdown(reply)
        except Exception as exc:  # noqa: BLE001
            st.error(f"Run failed: {exc}\n\nCheck the provider extra is installed and credentials are set (🔑 Credentials).")


def _history_panel():
    st.subheader("🕘 Prompt & interaction history")
    rows = [r for r in _log().events() if r.get("kind") == "run"]
    if not rows:
        st.info("No runs logged yet — use **Test run** to populate history.")
        return
    cc = st.columns(2)
    if cc[0].button("🗑️ Clear history"):
        _log().clear()
        st.rerun()
    cc[1].caption(f"{len(rows)} run(s) logged")
    for r in reversed(rows[-50:]):
        title = f"{r.get('ts','')[:19]} · {r.get('model','')} · {r.get('tokens_out',0)} out"
        if r.get("eval_score"):
            title += f" · rel {r['eval_score']:.1f}"
        with st.expander(title):
            if r.get("user_msg"):
                st.markdown(f"**User:** {r['user_msg']}")
            if r.get("response"):
                st.markdown(f"**Response:** {r['response']}")
            st.caption(
                f"tokens in/out: {r.get('tokens_in',0)}/{r.get('tokens_out',0)} · "
                f"latency: {r.get('latency_ms',0)}ms · cost: ${r.get('cost_usd',0):.5f}"
            )


def _eval_panel(provider: str, model: str):
    st.subheader("📏 Evaluation metrics")
    st.caption("Run a small dataset through the model and score relevance, latency, cost, and efficiency.")
    system_prompt = st.session_state.get("prompt_text", "")
    try:
        import pandas as pd

        default_df = pd.DataFrame(
            [{"input": "What can you help me with?", "criteria": "Mentions its actual capabilities"}]
        )
        edited = st.data_editor(default_df, num_rows="dynamic", key="eval_cases", use_container_width=True)
        cases = [{"input": r["input"], "criteria": r.get("criteria", "")}
                 for r in edited.to_dict("records") if str(r.get("input", "")).strip()]
    except Exception:  # noqa: BLE001 - pandas optional
        raw = st.text_area("One input per line", value="What can you help me with?")
        cases = [{"input": ln, "criteria": ""} for ln in raw.splitlines() if ln.strip()]

    if st.button("Run evals", type="primary") and cases:
        from agentx.insights import evaluate_dataset
        with st.spinner(f"Evaluating {len(cases)} case(s)…"):
            summary = evaluate_dataset(system_prompt, cases, provider=provider, model=model)
        m = st.columns(5)
        m[0].metric("Cases", summary.count)
        m[1].metric("Mean relevance", f"{summary.mean_relevance:.2f}")
        m[2].metric("Avg latency", f"{summary.avg_latency_ms} ms")
        m[3].metric("Total cost", f"${summary.total_cost_usd:.5f}")
        m[4].metric("Token efficiency", f"{summary.avg_token_efficiency:.2f}")
        try:
            import pandas as pd
            st.dataframe(pd.DataFrame([c.to_dict() for c in summary.per_case]), use_container_width=True)
        except Exception:  # noqa: BLE001
            st.write([c.to_dict() for c in summary.per_case])


def _trends_panel():
    st.subheader("📊 Usage & trends")
    log = _log()
    agg = log.aggregate()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Runs", agg["runs"])
    c2.metric("Total tokens", f"{agg['total_tokens']:,}")
    c3.metric("Total cost", f"${agg['total_cost_usd']:.4f}")
    c4.metric("Avg latency", f"{agg['avg_latency_ms']} ms")

    # Response-cache savings — always render (0 when the cache is empty/absent).
    st.markdown("###### 💾 Response cache")
    try:
        from agentx.cache import cache_stats, clear_cache

        cs = cache_stats(_CACHE_PATH) if _CACHE_PATH.exists() else {
            "hit_rate": 0.0, "hits": 0, "misses": 0, "tokens_saved": 0, "est_usd_saved": 0.0,
        }
        d1, d2, d3, d4 = st.columns(4)
        d1.metric("Hit rate", f"{cs['hit_rate']:.0%}", help=f"{cs['hits']} hits / {cs['misses']} misses")
        d2.metric("Tokens saved", f"{cs['tokens_saved']:,}")
        d3.metric("Est. $ saved", f"${cs['est_usd_saved']:.4f}")
        if d4.button("Clear cache") and _CACHE_PATH.exists():
            clear_cache(_CACHE_PATH)
            st.rerun()
    except Exception:  # noqa: BLE001
        st.caption("Cache stats unavailable.")

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
        if "eval_score" in df.columns and df["eval_score"].fillna(0).gt(0).any():
            st.markdown("###### Relevance score per run")
            st.line_chart(df[["eval_score"]], height=160)
    except Exception:  # noqa: BLE001 - pandas optional
        st.write(rows[-20:])


# --------------------------------------------------------------------------- #
def main():
    provider, model, store, path, agent_name = _sidebar()

    st.title("🧬 Prompt Observability, Optimization & Evaluation")
    st.caption("Pick a provider/model, add your key, edit a prompt, see token/cost/limits live, "
               "optimize, test, evaluate, and track history — all in one place.")

    text = st.text_area(
        "System prompt", value=st.session_state.get("prompt_text", ""),
        height=220, key="prompt_text",
        placeholder="You are a helpful assistant. Your goal is to…",
    )

    _metrics_row(text, model)
    st.divider()

    tabs = st.tabs(["🔎 Analysis", "✨ Optimize", "▶️ Test run", "📏 Evals", "🕘 History", "📊 Trends"])
    with tabs[0]:
        _analysis_panel(text, model)
    with tabs[1]:
        _optimize_panel(text, provider, model, store, path, agent_name)
    with tabs[2]:
        _run_panel(text, provider, model)
    with tabs[3]:
        _eval_panel(provider, model)
    with tabs[4]:
        _history_panel()
    with tabs[5]:
        _trends_panel()


main()
