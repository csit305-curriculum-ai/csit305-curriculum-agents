"""CSIT305 demo: real retrieval + coverage gate + replayed Condition A/B outputs.

Run:   streamlit run demo/app.py              (replay only, default; no API calls)
       streamlit run demo/app.py -- --live    (allows a NEW DeepSeek call per click; off by default,
                                               do not use until the MoE licence is confirmed)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
from cagents.run import load_tasks  # noqa: E402
from demo import loader  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--live", action="store_true")
LIVE = ap.parse_known_args()[0].live

st.set_page_config(page_title="CSIT305 curriculum agents - demo", layout="wide")
st.title("Curriculum-grounded lesson planning: A vs B (vs C)")
st.caption("CSIT305 research artefact. Retrieval and gate run LIVE on this machine. "
           + ("LIVE generation ENABLED." if LIVE else "Model outputs are REPLAYED from recorded runs; no new API calls."))


@st.cache_resource(show_spinner="Loading bge-m3 and the Chroma index...")
def get_index():
    from cagents.retrieval import BGEM3Embedder, Index
    return Index(BGEM3Embedder())


tasks = {t["task_id"]: t for t in load_tasks(None)}
REFUSAL = "TEST001 (G4 Science, outcome removed)"
choice = st.sidebar.selectbox("Task", [REFUSAL] + list(tasks), index=1 + list(tasks).index("G3M-P1"))
st.sidebar.markdown("**Mode:** " + ("live generation (--live)" if LIVE else "replay (default)"))

if choice == REFUSAL:
    rows = loader.test001_rows()
    st.subheader("TEST 001: signature failure test (recorded)")
    st.write("The Grade 4 Science outcome SC-4.4.3.2.2 was removed from a copy of the corpus, then Condition B was "
             "asked for it 10 times. Expected: refuse before generation.")
    if rows:
        ok = sum(r["pass"] == "True" for r in rows)
        st.metric("B refused correctly", f"{ok}/{len(rows)}")
        st.error(f"Displayed to teacher: {rows[0]['displayed_response']}")
        st.json({k: rows[0][k] for k in ("status", "generation_called", "modified_corpus_hash", "elapsed_s")})
        st.dataframe([{k: r[k] for k in ("attempt", "status", "generation_called", "elapsed_s", "pass")} for r in rows])
    else:
        st.warning("runs/test001_science/test001_results.csv not found.")
    crows = loader.test001_c_rows()
    if crows:
        okc = sum(r["pass"] == "True" for r in crows)
        st.metric("C refused correctly (TEST 006, offline: gate refuses before any model call)", f"{okc}/{len(crows)}")
        st.caption(f"B + C combined: {ok + okc if rows else okc}/{len(rows) + len(crows)} safe refusals (target 20/20).")
    else:
        st.info("Condition C TEST 001 replay not found (runs/test001_science_c).")
    st.stop()

t = tasks[choice]
st.subheader(f"{t['task_id']}: {t['topic']}")
st.write(f"Grade {t['grade']} {t['subject']} | outcome `{t['outcome_id']}` | split: {t['split']} | {t['duration_min']} min")

st.markdown("### 1. Retrieval (live, bge-m3 + Chroma, top-5) and coverage gate (DEC 013)")
try:
    idx = get_index()
    b = idx.retrieve(t["topic"], t["subject"], t["grade"], outcome_id=t.get("outcome_id"))
except Exception as e:  # index not built on this machine
    b = None
    st.warning(f"Retrieval unavailable ({e}). Build the index first: see README 'Demo'.")
if b is not None:
    if b.status == "ok":
        st.success(f"Gate PASS: outcome {t['outcome_id']} is in the Grade {t['grade']} {t['subject']} inventory "
                   f"and in the retrieved text. Retrieval {b.retrieval_latency_s:.2f}s.")
    else:
        st.error(f"Gate REFUSE ({b.status}): {b.reason}")
    for c in b.chunks:
        with st.expander(f"{c['chunk_id']}  score {c['score']}  outcomes {', '.join(c['outcome_ids'][:6])}"):
            st.text(c["text"][:1500])
    fh = loader.frozen_hash(t["task_id"])
    st.markdown("### 2. Frozen evidence packet")
    st.code(f"live   {b.bundle_hash}\nfrozen {fh or 'no frozen packet for this task'}")
    if fh:
        (st.success if fh == b.bundle_hash else st.error)(
            "Live packet reproduces the frozen packet." if fh == b.bundle_hash else "MISMATCH: a real run would stop here.")

st.markdown("### 3. Outputs")
rec = loader.recorded_results()


def show(cond: str):
    st.markdown(f"#### Condition {cond}" + (" (no retrieval)" if cond == "A" else " (evidence + cited chunk IDs)"))
    runs = rec.get((t["task_id"], cond), [])
    if not runs:
        st.info("No recorded run for this task.")
        return
    labels = [f"{r['_source'].split('/')[1]}: {r['status']}" for r in runs]
    i = st.radio("Recorded run", range(len(runs)), format_func=lambda j: labels[j], key=cond, horizontal=True)
    r = runs[i]
    st.warning(f"REPLAYED recorded output from {r['_source']} (not generated now)")
    st.caption(f"status {r['status']} | tokens in/out {r.get('prompt_tokens') or r.get('total_prompt_tokens')}/"
               f"{r.get('completion_tokens') or r.get('total_completion_tokens')} | reason: {r.get('reason') or '-'}")
    out = r.get("output")
    if isinstance(out, dict):
        st.markdown(f"**{out.get('title', '')}**")
        for o in (out.get("planning") or {}).get("objectives", []):
            st.markdown(f"- {o['objective_id']}: {o['text']}  " + (f"`{', '.join(o.get('citations') or [])}`" if o.get("citations") else ""))
        with st.expander("Full JSON"):
            st.json(out)
    elif r["status"] != "ok":
        st.error(f"Recorded run did not produce a valid lesson ({r['status']}).")


def show_c():
    st.markdown("#### Condition C (four agents)")
    st.warning("OFFLINE / SCRIPTED MODEL RESPONSES: pipeline demo only, not model output, not a quality result (TEST 006).")
    c = loader.c_offline_run(t["task_id"])
    if not c:
        st.info("No offline C run for this task (runs: G3M-P1, G3S-P1, G4M-P1).")
        return
    j = c["job"]
    st.caption(f"source {c['_source']} | status {j['status']} | model calls {j.get('model_calls', j.get('attempts'))} "
               f"(no 5th call) | tokens in/out {j['prompt_tokens']}/{j['completion_tokens']} | est. cost ${float(j['cost_usd']):.4f}")
    if c["nodes"]:
        st.markdown("**Four-agent trace**")
        st.dataframe([{"#": n["node_pos"], "node": n["node"], "status": n["status"], "attempts": n["attempts"],
                       "tokens in": n["prompt_tokens"], "tokens out": n["completion_tokens"], "cost $": n["cost_usd"]}
                      for n in c["nodes"]], hide_index=True)
    out = j.get("output")
    if isinstance(out, dict):
        st.markdown(f"**Assembled pack (Python, no model call): {out.get('title', '')}**")
        for o in out["planning"]["objectives"]:
            st.markdown(f"- {o['objective_id']}: {o['text']}  `{', '.join(o['citations'])}`")
        with st.expander("Full assembled JSON"):
            st.json(out)


ca, cb, cc = st.columns(3)
with ca:
    show("A")
with cb:
    show("B")
with cc:
    show_c()

if LIVE:
    st.markdown("### Live generation (--live)")
    st.warning("Sends MoE curriculum text to DeepSeek. Do not use until the licence is confirmed.")
    cond = st.selectbox("Condition", ["A", "B"])
    if st.button("Generate now") and os.environ.get("DEEPSEEK_API_KEY"):
        from cagents.conditions import TraceLogger, run_condition
        from cagents.llm import DeepSeekClient
        (ROOT / "runs" / "demo_live").mkdir(parents=True, exist_ok=True)
        res = run_condition(t, cond, DeepSeekClient(), TraceLogger(ROOT / "runs" / "demo_live" / "trace.jsonl"),
                            bundle=b if cond == "B" else None)
        st.json(res.get("output") or {"status": res["status"], "reason": res.get("reason")})
