"""Errors and old queues must never launch GitHub or contact a report server."""
import importlib.util
import io
import json
from pathlib import Path


def test_startup_and_errors_stay_local_with_old_pending_reports(tmp_path, monkeypatch):
    source = Path(__file__).resolve().parents[1] / "snapgen_modules/snapgen_error_reporter.py"
    spec = importlib.util.spec_from_file_location("local_reporter_test", source)
    reporter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reporter)
    started = []

    class Thread:
        def __init__(self, target, name=None, **kwargs):
            self.name = name

        def start(self):
            started.append(self.name)

    def forbidden(*args, **kwargs):
        raise AssertionError("Local diagnostics tried to start a process or send data")

    monkeypatch.setattr(reporter.threading, "Thread", Thread)
    monkeypatch.setattr(reporter.subprocess, "Popen", forbidden)
    monkeypatch.setattr(reporter.subprocess, "run", forbidden)
    monkeypatch.setattr(reporter.faulthandler, "enable", lambda **kwargs: None)
    monkeypatch.setattr(reporter.atexit, "register", lambda *args: None)
    data = tmp_path / "snapgen_data/error_reports"
    data.mkdir(parents=True)
    queued = '{"kind":"old pending report"}\n'
    (data / "pending.jsonl").write_text(queued, encoding="utf-8")
    (data / "sending.jsonl").write_text(queued, encoding="utf-8")
    try:
        reporter.configure(tmp_path)
        reporter.report_log("ERROR: cannot render token=secret-value", "video")
        reporter.report_exception("worker", ValueError, ValueError("failed locally"), None)
        stream = io.StringIO()
        reporter._ReportingStream(stream, "page").write("WARNING: local issue\n")
        assert stream.getvalue() == "WARNING: local issue\n"
        rows = [json.loads(line) for line in (data / "pending.jsonl").read_text(encoding="utf-8").splitlines()]
        assert [row["kind"] for row in rows] == ["old pending report", "video", "worker", "page"]
        assert "secret-value" not in json.dumps(rows)
        assert (data / "sending.jsonl").read_text(encoding="utf-8") == queued
        assert not any(name in started for name in ("SnapGenErrorRetry", "SnapGenErrorReporter", "SnapGenGitHubLogin"))
        reporter.mark_clean_shutdown()
        assert json.loads((data / "active_session.json").read_text(encoding="utf-8"))["clean"] is True
    finally:
        if reporter._fatal_stream:
            reporter._fatal_stream.close()


def test_setup_and_repair_no_longer_require_reporter_github_login():
    root = Path(__file__).resolve().parents[1]
    setup = (root / "setup_and_run.bat").read_text(encoding="utf-8")
    repair = (root / "snapgen_modules/snapgen_system_repair.py").read_text(encoding="utf-8")
    assert "gh auth login" not in setup
    assert "GitHub.cli" not in setup
    assert "_ensure_gh" not in repair
