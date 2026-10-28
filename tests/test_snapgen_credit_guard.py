import base64
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from test_video_auto_scene_provider import N, Widget, batch_scope, chooser_scope, load
from snapgen_credit_guard import (credit_consent_required, credit_warning_text,
                                  image_billing, record_image_billing)


@pytest.mark.parametrize("cost,paused", [(0, False), (1, False), (10, False), (10.01, True), (15, True)])
def test_threshold_is_strictly_over_ten_and_batch_sum_is_not_an_image(cost, paused):
    project = {}
    for index in range(5):
        record_image_billing(project, f"scene_{index}", {"task_id": str(index), "used_credit": cost})
    assert credit_consent_required(project) == paused


def test_real_baseline_ratio_persistence_and_fresh_consent():
    project = {}
    record_image_billing(project, "normal", {"task_id": "a", "used_credit": 1})
    record_image_billing(project, "expensive", {"task_id": "b", "used_credit": 15})
    loaded = json.loads(json.dumps(project))
    assert "15 เท่า" in credit_warning_text(loaded["snapgen_credit_warning"])
    assert credit_consent_required(loaded)
    assert not credit_consent_required(loaded, {"ceiling": 15})
    record_image_billing(loaded, "higher", {"task_id": "c", "used_credit": 16})
    assert credit_consent_required(loaded, {"ceiling": 15})
    record_image_billing(loaded, "late-cheap", {"task_id": "d", "used_credit": 1})
    assert credit_consent_required(loaded, {"ceiling": 15})
    assert credit_consent_required(json.loads(json.dumps(loaded)))


def test_unknown_charge_is_never_reported_as_tenfold_or_silently_accepted():
    project = {}
    record_image_billing(project, "unknown", {"task_id": "a", "used_credit": None})
    assert "เท่า" not in credit_warning_text(project["snapgen_credit_warning"])
    assert credit_consent_required(project, {"ceiling": 100})
    assert not credit_consent_required(project, {"allow_unknown": True})
    record_image_billing(project, "actual", {"task_id": "b", "used_credit": 20})
    assert credit_consent_required(project, {"allow_unknown": True})


def test_known_price_acceptance_does_not_approve_unknown_price():
    project = {}
    record_image_billing(project, "expensive", {"task_id": "a", "used_credit": 15})
    record_image_billing(project, "unknown", {"task_id": "b", "used_credit": None})
    assert credit_consent_required(project, {"ceiling": 15})
    assert not credit_consent_required(project, {"ceiling": 15, "allow_unknown": True})


@pytest.mark.parametrize("bad", [None, True, "NaN", "infinity", -2, "bad"])
def test_only_valid_job_used_credit_is_a_price(bad):
    result = image_billing({"uuid": "job", "used_credit": bad, "balance": 100, "cost": 50})
    assert result == {"task_id": "job", "used_credit": None}
    assert image_billing({"data": {"uuid": "job", "used_credit": "12.5"}})["used_credit"] == 12.5


@pytest.mark.parametrize("decision", ["chrome", "accept", "cancel"])
def test_red_dialog_requires_unchecked_consent_before_api(tmp_path, decision):
    scope, dialogs, logs = chooser_scope(tmp_path, [])
    project = scope["state"]["project"]
    record_image_billing(project, "scene_001", {"task_id": "a", "used_credit": 15})
    labels, windows = [], []
    class Var:
        def __init__(self, **kwargs): self.value = kwargs.get("value", False)
        def get(self): return self.value
        def set(self, value): self.value = value
    class Window(Widget):
        def __init__(self, *args):
            self.buttons = {}; self.closed = False; windows.append(self)
        def title(self, *args): pass
        def transient(self, *args): pass
        def resizable(self, *args): pass
        def bind(self, name, callback): self.callback = callback
        def destroy(self):
            self.closed = True; self.callback(SimpleNamespace(widget=self))
        def grab_set(self):
            api = self.buttons["ยอมรับและใช้ SnapGen API ต่อ"]
            assert api.options["state"] == "disabled" and not self.consent.get()
            api.command()  # Even an invoked callback cannot bypass an unchecked box.
            assert not self.closed and "snapgen_credit_acceptance" not in scope["state"]
            if decision == "accept":
                self.consent.set(True); self.toggle()
                assert api.options["state"] == "normal"
                api.command()
            elif decision == "chrome": self.buttons["เปลี่ยนเป็น GPT Chrome"].command()
            else: self.destroy()
    class Button(Widget):
        def __init__(self, win, text, command, **kwargs):
            self.options = kwargs; self.command = command; win.buttons[text] = self
        def config(self, **kwargs): self.options.update(kwargs)
    class Label(Widget):
        def __init__(self, *args, **kwargs): labels.append(kwargs)
    class Checkbox(Widget):
        def __init__(self, win, variable, command, **kwargs):
            win.consent = variable; win.toggle = command
    scope["tk"] = SimpleNamespace(Toplevel=Window, Label=Label, Button=Button,
                                  Checkbutton=Checkbox, BooleanVar=Var)
    scope["refresh_snapgen_credit_warning"] = lambda: None
    load(scope, "confirm_snapgen_credit_warning")
    project["image_stage_providers"] = {"images": "snapgen"}
    confirm = lambda: scope["image_provider_for"]("images")
    if decision == "cancel":
        with pytest.raises(N.Stopped): confirm()
    else:
        assert confirm() == ("snapgen" if decision == "accept" else "gpt_web")
    assert any(label.get("fg") == "#B91C1C" for label in labels)
    assert credit_consent_required(project, scope["state"].get("snapgen_credit_acceptance")) == (decision != "accept")
    assert project["snapgen_credit_warning"]["used_credit"] == 15
    if decision == "accept":
        assert confirm() == "snapgen" and len(windows) == 1
        scope["state"].pop("snapgen_credit_acceptance")
        assert confirm() == "snapgen" and len(windows) == 2


def test_persisted_warning_restores_the_visible_banner(tmp_path):
    scope, dialogs, logs = chooser_scope(tmp_path, [])
    project = scope["state"]["project"]
    record_image_billing(project, "scene_001", {"task_id": "a", "used_credit": 15})
    scope["save_project"]()
    scope["state"]["project"] = json.loads((tmp_path / "project.json").read_text())
    class Banner(Widget):
        visible = False
        def pack(self, **kwargs): self.visible = True
        def pack_forget(self): self.visible = False
    scope["credit_warning_var"] = Widget()
    scope["credit_warning_label"] = Banner()
    refresh = load(scope, "refresh_snapgen_credit_warning")
    refresh()
    assert scope["credit_warning_label"].visible
    assert "15 เครดิต" in scope["credit_warning_var"].get()
    scope["state"]["snapgen_credit_acceptance"] = {"ceiling": 15}
    refresh()
    assert "ยอมรับค่าใช้จ่ายเฉพาะรอบทำงานนี้แล้ว" in scope["credit_warning_var"].get()


@pytest.mark.parametrize("cost", [15, None])
def test_expensive_or_unverified_result_is_saved_then_new_jobs_pause(tmp_path, monkeypatch, cost):
    scope, paths = batch_scope(tmp_path, 12)
    scope["IMAGES_PER_CHAT"] = 12
    shown = []
    scope["refresh_snapgen_credit_warning"] = lambda: shown.append(
        credit_warning_text(scope["state"]["project"]["snapgen_credit_warning"]))
    load(scope, "generate_via_snapgen"); load(scope, "make_image")
    buffer = io.BytesIO(); Image.new("RGB", (48, 64), "blue").save(buffer, "PNG")
    generated = buffer.getvalue(); requests = []
    def reply(request, **kwargs):
        requests.append(request)
        if request.get_method() == "POST":
            job = f"job-{sum(r.get_method() == 'POST' for r in requests)}"
            result = {"id": job, "status": "queued"}
        else:
            job = request.full_url.rsplit("/", 1)[-1]
            result = {"id": job, "status": "succeeded",
                      "charged_microusd": str(cost * 10000) if cost is not None else None,
                      "result": {"urls": ["data:image/png;base64," + base64.b64encode(generated).decode()]}}
        return io.BytesIO(json.dumps(result).encode())
    monkeypatch.setattr(N.urllib.request, "urlopen", reply)
    with pytest.raises(N.ImageProviderError): scope["stage_images"]()
    project = scope["state"]["project"]
    made = [scene for scene in project["scenes"] if scene.get("image")]
    assert 2 <= len(requests) <= 10 and len(requests) == 2 * len(made)
    assert all(Path(scene["image"]).read_bytes() == generated for scene in made)
    assert shown and credit_consent_required(project)
    saved = json.loads((tmp_path / "project.json").read_text())
    assert credit_consent_required(saved)
    count = len(requests)
    with pytest.raises(N.ImageProviderError):
        scope["generate_via_snapgen"]("retry", [], tmp_path, "retry", "9:16", api_context={"api_key": "test-key"})
    assert len(requests) == count


def test_history_lookup_confirms_cost_without_second_generation(tmp_path, monkeypatch):
    calls, records = [], []
    encoded = "data:image/png;base64," + base64.b64encode(b"generated-image").decode()
    def reply(request, **kwargs):
        calls.append(request)
        value = ({"id": "job-1", "status": "queued"} if request.get_method() == "POST"
                 else {"id": "job-1", "status": "succeeded", "charged_microusd": "140000",
                       "result": {"urls": [encoded]}})
        return io.BytesIO(json.dumps(value).encode())
    monkeypatch.setattr(N.urllib.request, "urlopen", reply)
    output = N.snapgen_image("scene", [], str(tmp_path), "scene", "9:16", "test-key", on_credit=records.append)
    assert [request.get_method() for request in calls] == ["POST", "GET"]
    assert calls[0].full_url == N.SNAPGEN_IMAGE_URL
    assert calls[-1].full_url.endswith("/tasks/job-1")
    assert records == [{"task_id": "job-1", "used_credit": 14}]
    assert Path(output).read_bytes() == b"generated-image"


def test_async_charge_is_reported_with_the_finished_image(tmp_path, monkeypatch):
    records = []
    encoded = "data:image/png;base64," + base64.b64encode(b"paid-image").decode()
    monkeypatch.setattr(N.urllib.request, "urlopen", lambda *args, **kwargs: io.BytesIO(json.dumps({
        "id": "job", "status": "succeeded", "charged_microusd": "150000",
        "result": {"urls": [encoded]}}).encode()))
    result = N.snapgen_image("scene", [], str(tmp_path), "scene", "9:16", "test-key", on_credit=records.append)
    assert Path(result).read_bytes() == b"paid-image"


def test_pretty_json_and_initial_zero_do_not_hide_the_final_charge(tmp_path, monkeypatch):
    records, calls = [], []
    encoded = "data:image/png;base64," + base64.b64encode(b"paid-image").decode()
    def reply(request, **kwargs):
        calls.append(request)
        payload = ({"id": "job", "status": "queued"} if request.get_method() == "POST" else
                   {"id": "job", "status": "succeeded", "charged_microusd": "180000",
                    "result": {"urls": [encoded]}})
        return io.BytesIO(json.dumps(payload, indent=2).encode())
    monkeypatch.setattr(N.urllib.request, "urlopen", reply)
    N.snapgen_image("scene", [], str(tmp_path), "scene", "9:16", "test-key", on_credit=records.append)
    assert records == [{"task_id": "job", "used_credit": 18}]
    assert len(calls) == 2


def test_successful_pretty_json_response_keeps_credit_and_image(tmp_path, monkeypatch):
    records = []
    encoded = "data:image/png;base64," + base64.b64encode(b"paid-image").decode()
    raw = json.dumps({"id": "job", "status": "succeeded", "charged_microusd": "120000",
                      "result": {"urls": [encoded]}}, indent=2)
    monkeypatch.setattr(N.urllib.request, "urlopen", lambda *args, **kwargs: io.BytesIO(raw.encode()))
    result = N.snapgen_image("scene", [], str(tmp_path), "scene", "9:16", "test-key", on_credit=records.append)
    assert records == [{"task_id": "job", "used_credit": 12}]
    assert Path(result).read_bytes() == b"paid-image"
