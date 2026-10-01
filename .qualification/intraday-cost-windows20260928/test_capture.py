import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("quote_window_capture", Path(__file__).with_name("run_capture.py"))
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)


def test_access_denial_is_saved_before_stop(tmp_path):
    path = tmp_path / "denied.json"
    with pytest.raises(PermissionError):
        capture.save_capture(path, {"status_code": 403, "raw_file": "preserved.json"})
    assert json.loads(path.read_text())["status_code"] == 403


def test_empty_terminal_page_completes_but_unattempted_window_remains(tmp_path, monkeypatch):
    monkeypatch.setattr(capture, "ROOT", tmp_path)
    (tmp_path / "raw.json").write_text(json.dumps({"quotes": {}, "next_page_token": None}))
    (tmp_path / "cost-a-page-1.capture.json").write_text(json.dumps({"status_code": 200, "raw_file": "raw.json"}))
    rows = capture.complete_denominator({"windows": [{"id": "a"}, {"id": "b"}]})
    assert rows[0]["complete"] is True
    assert rows[1]["complete"] is False and rows[1]["pages"] == []


def test_pending_token_never_becomes_complete(tmp_path, monkeypatch):
    monkeypatch.setattr(capture, "ROOT", tmp_path)
    (tmp_path / "raw.json").write_text(json.dumps({"quotes": {}, "next_page_token": "remaining"}))
    (tmp_path / "cost-a-page-1.capture.json").write_text(json.dumps({"status_code": 200, "raw_file": "raw.json"}))
    assert capture.complete_denominator({"windows": [{"id": "a"}]})[0]["complete"] is False


def test_transport_failure_preserves_all_144_cells(tmp_path, monkeypatch):
    analyzer_spec = importlib.util.spec_from_file_location("quote_failure_analysis", Path(__file__).with_name("cost-analyze.py"))
    analyzer = importlib.util.module_from_spec(analyzer_spec)
    analyzer_spec.loader.exec_module(analyzer)
    analyzer.ROOT = tmp_path
    monkeypatch.setattr(capture, "ROOT", tmp_path)
    windows = [{"id": str(i), "start": "2020-01-02T15:46:00+00:00", "end": "2020-01-02T15:47:00+00:00"} for i in range(24)]
    definition = {"windows": windows, "symbols": ["AAPL", "MSFT", "F", "T", "HRL", "BANF"]}
    (tmp_path / "cost-definition.json").write_text(json.dumps(definition))
    name = "cost-0-page-1.capture.json"
    (tmp_path / name).write_text(json.dumps({"error": "ReadTimeout"}))
    summary = capture.complete_denominator(definition)
    assert summary[0]["pages"] == [] and summary[0]["request_attempts"] == [name]
    assert summary[0]["error"] == "ReadTimeout"
    analyzer.main()
    cells = json.loads((tmp_path / "cost-analysis.json").read_text())["cells"]
    assert len(cells) == 144 and all(not cell["pagination_complete"] for cell in cells)
