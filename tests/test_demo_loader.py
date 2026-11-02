"""Demo replay loader: real recorded data only, nothing invented."""
import json
from demo import loader


def test_summary_only_has_no_output(tmp_path):
    d = tmp_path / "runs" / "smoke_2"; d.mkdir(parents=True)
    (d / "summary.csv").write_text("task_id,condition,status\nG3M-P1,B,ok\n")
    rec = loader.recorded_results(tmp_path)
    assert rec[("G3M-P1", "B")][0]["output"] is None
    assert ("G3M-01", "A") not in rec  # no recorded run -> absent, never invented


def test_trace_preferred_and_newest_first(tmp_path):
    for name, status in (("smoke_2", "invalid_output"), ("smoke", "ok")):
        d = tmp_path / "runs" / name; d.mkdir(parents=True)
        (d / "trace.jsonl").write_text(json.dumps({"event": "attempt", "task_id": "X", "condition": "A"}) + "\n"
                                       + json.dumps({"event": "result", "task_id": "X", "condition": "A", "status": status}) + "\n")
    runs = loader.recorded_results(tmp_path)[("X", "A")]
    assert [r["status"] for r in runs] == ["invalid_output", "ok"]


def test_frozen_hash_from_manifest(tmp_path):
    p = tmp_path / "packets"; p.mkdir()
    (p / "freeze_manifest.json").write_text(json.dumps({"packets": {"T": {"bundle_hash": "abc"}}}))
    assert loader.frozen_hash("T", tmp_path) == "abc" and loader.frozen_hash("U", tmp_path) is None


def test_real_test001_rows_all_refused():
    rows = loader.test001_rows()
    assert len(rows) == 10 and all(r["status"] == "insufficient_evidence" and r["generation_called"] == "False" for r in rows)
