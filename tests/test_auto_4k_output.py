"""4K sizing and dispatch must preserve portrait, audio, timing and existing assets."""
import ast
import copy
import io
from pathlib import Path
from types import SimpleNamespace

import pytest

from test_auto_video_merge import merge_scope
import ai_slow2x as A


@pytest.mark.parametrize("size,target", [((1280, 720), (3840, 2160)), ((720, 1280), (2160, 3840)),
                                        ((3840, 2160), (3840, 2160))])
def test_4k_target_fits_content_without_stretching_or_changing_orientation(size, target):
    assert A._video_4k_size(*size) == target
    assert A._fit_video_size(*size, *target) == target
    assert A._fit_video_size(1264, 720, 3840, 2160) == (3792, 2160)


@pytest.mark.parametrize("size", [(1280, 720), (720, 1280)])
def test_topaz_4k_spatial_upscale_keeps_audio_without_slow_motion(tmp_path, monkeypatch, size):
    src = tmp_path / "spoken.mp4"
    src.write_bytes(b"original spoken clip")
    commands = []

    target = A._video_4k_size(*size)

    def run(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0, stderr=f"Duration: 00:00:02.00\nVideo: h264, {size[0]}x{size[1]}\nAudio: aac", stdout="")

    class ProgressProcess:
        def __init__(self, command, **kwargs):
            commands.append(command)
            Path(command[-1]).write_bytes(b"upscaled output")
            self.stdout = io.StringIO("out_time_us=1000000\nprogress=continue\nout_time_us=2000000\nprogress=end\n")
            self.stderr = io.StringIO("")
            self.returncode = 0

        def poll(self):
            return self.returncode

        def wait(self, timeout=None):
            return self.returncode

        def kill(self):
            self.returncode = -9

    monkeypatch.setattr(A, "_video_ok", lambda path: Path(path).is_file())
    monkeypatch.setattr(A, "ensure_ffmpeg_tool", lambda **kwargs: "ffmpeg")
    monkeypatch.setattr(A, "_video_dimensions", lambda _ffmpeg, path: size if Path(path) == src else target)
    monkeypatch.setattr(A, "_video_duration_seconds", lambda *args: 2.0)
    monkeypatch.setattr(A, "_topaz_dirs", lambda: (tmp_path / "topaz.exe", tmp_path))
    monkeypatch.setattr(A.subprocess, "run", run)
    monkeypatch.setattr(A.subprocess, "Popen", ProgressProcess)
    progress, logs = [], []
    result = A.upscale_video_4k(src, log=logs.append, progress=lambda backend, pct: progress.append((backend, pct)))
    encode = next(cmd for cmd in commands if "-vf" in cmd)
    vf = encode[encode.index("-vf") + 1]
    w, h = A._video_4k_size(*size)
    assert f"w={w}:h={h}" in vf and f"pad={w}:{h}" in vf
    assert "tvai_fi" not in vf and "setpts" not in vf and "-af" not in encode
    assert encode[encode.index("-c:a") + 1] == "aac"
    assert "-progress" in encode and "pipe:1" in encode
    assert ("Topaz Video AI", 50) in progress and progress[-1] == ("Topaz Video AI", 100)
    assert any("Topaz Video AI ✓" in line for line in logs)
    assert Path(result).name == "spoken_4K.mp4"
    assert src.read_bytes() == b"original spoken clip"


def test_missing_topaz_reports_ffmpeg_backend_truthfully(tmp_path, monkeypatch):
    src = tmp_path / "clip.mp4"
    src.write_bytes(b"input")
    target = (3840, 2160)

    def run(command, **kwargs):
        return SimpleNamespace(returncode=0,
                               stderr="Duration: 00:00:01.00\nVideo: h264, 1280x720\nAudio: aac",
                               stdout="")

    class ProgressProcess:
        def __init__(self, command, **kwargs):
            Path(command[-1]).write_bytes(b"ffmpeg upscaled")
            self.stdout = io.StringIO("out_time_us=500000\nprogress=continue\nout_time_us=1000000\nprogress=end\n")
            self.stderr = io.StringIO("")
            self.returncode = 0

        def poll(self):
            return self.returncode

        def wait(self, timeout=None):
            return self.returncode

        def kill(self):
            self.returncode = -9

    monkeypatch.setattr(A, "_video_ok", lambda path: Path(path).is_file())
    monkeypatch.setattr(A, "ensure_ffmpeg_tool", lambda **kwargs: "ffmpeg")
    monkeypatch.setattr(A, "_video_dimensions", lambda _ffmpeg, path: (1280, 720) if Path(path) == src else target)
    monkeypatch.setattr(A, "_video_duration_seconds", lambda *args: 1.0)
    monkeypatch.setattr(A, "_topaz_dirs", lambda: None)
    monkeypatch.setattr(A.subprocess, "run", run)
    monkeypatch.setattr(A.subprocess, "Popen", ProgressProcess)
    logs, progress = [], []
    output = A.upscale_video_4k(src, log=logs.append, progress=lambda backend, pct: progress.append((backend, pct)))
    assert A._video_dimensions("ffmpeg", output) == target
    assert progress and {backend for backend, _ in progress} == {"FFmpeg"}
    assert any("FFmpeg 4K ✓" in line for line in logs)
    assert not any("Topaz Video AI ✓" in line for line in logs)


@pytest.mark.parametrize("aspect,expected", [("16:9", [3840, 2160]), ("9:16", [2160, 3840])])
def test_final_merge_uses_4k_without_regenerating_assets(tmp_path, aspect, expected):
    ns, logs, commands = merge_scope(tmp_path)
    project = ns["state"]["project"]
    project["aspect"] = aspect
    original = copy.deepcopy(project["scenes"])
    fitted = []
    ns["fitted_clip"] = lambda scene, length, width, height: (fitted.append([width, height]) or scene["clip"], "null")
    ns["stage_video"]()
    assert fitted == [expected, expected]
    assert project["last_video_size"] == expected
    assert project["scenes"] == original
    assert commands


def test_download_dispatch_uses_4k_and_does_not_skip_an_old_topaz2x_clip(tmp_path, monkeypatch):
    src = tmp_path / "clip_Slow2x_Topaz2x.mp4"
    src.write_bytes(b"old 2x")
    calls = []
    def upscale(path, output_video=None, log=None, progress=None):
        calls.append(path)
        Path(output_video).write_bytes(b"new 4k")
        return output_video
    monkeypatch.setattr(A, "upscale_video_4k", upscale)
    tree = ast.parse((Path(__file__).resolve().parents[1] / "snapgen_gui_v2.py").read_text(encoding="utf-8-sig"))
    node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_auto_upscale_video_1080p")
    ns = dict(Path=Path, g={"_auto_video_upscale_4k_override": True}, EXPORT_VIDEO=tmp_path,
              _upscale_1080_enabled=lambda: True)
    exec(compile(ast.Module(body=[node], type_ignores=[]), "upscale", "exec"), ns)
    output = ns[node.name](src)
    assert calls == [str(src)] and Path(output).stem.endswith("_4K")


def test_auto_postprocess_is_queued_without_waiting_for_the_next_clip(tmp_path):
    source = tmp_path / "downloaded.mp4"
    source.write_bytes(b"source")
    events, logs, progress = [], [], []

    class DeferredFuture:
        def __init__(self, fn):
            self.fn, self.done = fn, False
            self.value = None

        def result(self):
            if not self.done:
                self.value = self.fn()
                self.done = True
            return self.value

    class DeferredPool:
        def __init__(self):
            self.future = None

        def submit(self, fn):
            self.future = DeferredFuture(fn)
            return self.future

    pool = DeferredPool()
    slow_output = tmp_path / "downloaded_Slow2x_Topaz4K.mp4"

    def slow(path, **kwargs):
        events.append(("slow", kwargs))
        slow_output.write_bytes(b"slow and topaz 4k")
        kwargs["progress"]("Topaz Video AI (Slow + 4K)", 50)
        kwargs["progress"]("Topaz Video AI (Slow + 4K)", 100)
        return str(slow_output)

    tree = ast.parse((Path(__file__).resolve().parents[1] / "snapgen_gui_v2.py").read_text(encoding="utf-8-sig"))
    node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_queue_auto_video_postprocess")
    g = {
        "_auto_video_postprocess_pool": pool,
        "_auto_video_progress": lambda *args: progress.append(args),
    }
    ns = {
        "g": g, "Path": Path, "threading": __import__("threading"),
        "_slow2x_mod": SimpleNamespace(make_ai_slow2x=slow,
                                        ensure_ffmpeg_tool=lambda **kwargs: "ffmpeg",
                                        _video_dimensions=lambda ffmpeg, path: (3840, 2160)),
        "_auto_upscale_video_1080p": lambda path, **kwargs: path,
        "_mute_video_stream_copy": lambda path, **kwargs: path,
    }
    exec(compile(ast.Module(body=[node], type_ignores=[]), "auto_postprocess", "exec"), ns)
    returned = ns[node.name](str(source), 1, 7, True, True, True, False, logs.append)
    assert returned == str(source)
    assert pool.future is not None and not pool.future.done
    assert events == []  # submitting the background job returned before local rendering ran
    assert g["_auto_video_postprocess_jobs"][str(source.resolve())]["future"] is pool.future
    result = pool.future.result()
    assert events[0][1]["upscale_4k"] is True
    assert result == {"path": str(slow_output), "backend": "Topaz Video AI (Slow + 4K)"}
    assert progress == [(1, 7, "Topaz Video AI (Slow + 4K)", 50),
                        (1, 7, "Topaz Video AI (Slow + 4K)", 100)]


def test_auto_slot_releases_generation_after_download_while_credit_check_continues():
    tree = ast.parse((Path(__file__).resolve().parents[1] / "snapgen_gui_v2.py").read_text(encoding="utf-8-sig"))
    handler = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "on_generate_slot")
    worker = next(n for n in ast.walk(handler) if isinstance(n, ast.FunctionDef) and n.name == "worker")
    nodes = list(ast.walk(worker))
    poll = next(n for n in nodes if isinstance(n, ast.Call) and "poll_and_download" in ast.unparse(n))
    release = next(n for n in nodes if isinstance(n, ast.If) and ast.unparse(n.test) == "auto_pipeline"
                   and "slot_busy" in ast.unparse(n) and "False" in ast.unparse(n))
    credit = next(n for n in nodes if isinstance(n, ast.Call) and "_fetch_credit_after_deduction" in ast.unparse(n))
    assert poll.lineno < release.lineno < credit.lineno
    assert "is slot_job_token" in ast.unparse(worker)


def test_stage_clips_waits_for_background_upscale_before_final_merge():
    root = Path(__file__).resolve().parents[1]
    tree = ast.parse((root / "snapgen_modules" / "snapgen_page_narrate.py").read_text(encoding="utf-8-sig"))
    stage = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "stage_clips")
    video = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "stage_video")
    stage_text, video_text = ast.unparse(stage), ast.unparse(video)
    assert "_auto_video_pipeline_async" in stage_text and "= True" in stage_text
    assert "finalize_auto_video_postprocesses()" in stage_text
    assert "_auto_video_postprocess_finalizer" in video_text
    assert video_text.index("finish_postprocess()") < video_text.index("relink_or_report_missing_clips")
