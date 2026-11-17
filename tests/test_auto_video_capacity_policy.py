"""SnapGen video jobs may be retried only on terminal zero-credit capacity receipts."""
import pytest
from test_video_auto_scene_provider import N


@pytest.mark.parametrize("receipt", [
    {"status": 1, "used_credit": 0, "error_message": "high traffic"},
    {"status": 2, "used_credit": 0, "error_message": "high traffic"},
    {"status": 3, "used_credit": 2, "error_message": "high traffic"},
    {"status": 3, "error_message": "high traffic"},
    {"status": 3, "used_credit": "unknown", "error_message": "high traffic"},
    {"status": 3, "used_credit": 0, "error_message": "The prompt violates content moderation policies"},
    {"status": 3, "used_credit": 0, "error_message": "other provider failure"},
    None,
    {},
])
def test_never_retry_ambiguous_paid_or_policy_job(receipt):
    assert not N.snapgen_terminal_zero_credit_capacity(receipt)


@pytest.mark.parametrize("failure", [
    "The server currently is experiencing high traffic. Please try again.",
    "Too many requests",
    "rate limit",
    "service temporarily unavailable",
    "model_under_maintenance",
])
def test_confirmed_capacity_failure_is_safe_to_defer(failure):
    assert N.snapgen_terminal_zero_credit_capacity({
        "status": 3, "used_credit": 0, "error_message": failure
    })
