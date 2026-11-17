"""Run the real pipeline worker without media generation or UI."""
import pytest

from test_auto_video_merge import Value
from test_video_auto_scene_provider import N, load


@pytest.mark.parametrize("review,only,planned,confirm", [(False, None, False, False),
                        (True, None, False, False), (True, None, True, True),
                        (False, "images", False, True)])
def test_auto_only_pauses_for_requested_review(review, only, planned, confirm):
    calls = []
    stages = [(key, key, 1) for key in ("plan", "storyboard", "images", "motion", "clips", "video")]
    project = {"done": {"plan": True} if planned else {}}
    noop = lambda *args, **kwargs: None
    scope = dict(vars(N), video_mode=True, project=project, state={"busy": True},
                 only=only, character_limit=None, stages=stages,
                 review_var=Value(review), stage_var=Value(), detail_var=Value(),
                 start_btn=Value(), bar=Value(), g={},
                 ui=lambda fn, *args: fn(*args), refresh_snapgen_credit_warning=noop,
                 image_provider_for=noop, confirm_credits=lambda **kw: calls.append("confirm") or True,
                 refresh_stages=noop, log=noop, save_project=noop, refresh_all=noop,
                 set_progress=noop, ask_image_limit_fallback=lambda *args: False)
    scope["STAGE_FUNCS"] = {key: lambda k=key: calls.append(k) for key, _, _ in stages}
    load(scope, "worker", parent="start_pipeline")()
    if review and not planned:
        assert calls == ["plan"]
        assert project["done"] == {"plan": True}
    elif only:
        assert calls == ["confirm", "images"]
    elif planned:
        assert calls == ["confirm"] + [key for key, _, _ in stages if key not in ("plan", "motion")]
        assert project["done"]["motion"] and project["done"]["clips"]
        assert project["done"]["video"] is True
    else:
        assert calls == [key for key, _, _ in stages if key != "motion"]
        assert project["done"]["motion"] and project["done"]["clips"]
        assert project["done"]["video"] is True
    assert ("confirm" in calls) is confirm
    assert scope["state"]["busy"] is False

def test_effect_selection_always_stops_before_render():
    """Even a confirmed SFX choice must not start the merge automatically."""
    calls = []
    noop = lambda *args, **kwargs: None
    project = {"done": {"clips": True}}
    stages = [("effects", "เลือกเสียงเอฟเฟกต์", 1), ("video", "ตัดต่อ", 1)]
    scope = dict(vars(N), video_mode=True, project=project,
                 state={"busy": True, "effect_review_pending": True},
                 only=None, character_limit=None, stages=stages,
                 review_var=Value(False), stage_var=Value(), detail_var=Value(),
                 start_btn=Value(), bar=Value(), g={},
                 ui=lambda fn, *args: fn(*args), refresh_snapgen_credit_warning=noop,
                 image_provider_for=noop, confirm_credits=lambda **kw: True,
                 refresh_stages=noop, log=noop, save_project=noop, refresh_all=noop,
                 set_progress=noop, ask_image_limit_fallback=lambda *args: False)
    scope["STAGE_FUNCS"] = {"effects": lambda: calls.append("effects"),
                            "video": lambda: calls.append("video")}
    load(scope, "worker", parent="start_pipeline")()
    assert calls == ["effects"]
    assert project["done"]["effects"] is True
    assert project["done"].get("video") is None
    assert project["effect_review_pending"] is True
    assert scope["state"]["busy"] is False
