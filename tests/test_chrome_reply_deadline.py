from pathlib import Path
import re


def test_reply_timeout_cannot_be_extended_by_rate_limit_backoff():
    source = (Path(__file__).resolve().parents[1] / "snapgen_modules/chrome_ext/background.js").read_text(encoding="utf-8")
    poll = source[source.index("let deadline = Date.now() +"):source.index("async function pageSend") ]
    assert "while (Date.now() < deadline)" in poll
    backoff = poll[poll.index("if (result.rate_limited)"):poll.index("throttles = 0;", poll.index("if (result.rate_limited)"))]
    assert "deadline =" not in backoff and "deadline +=" not in backoff
    assert "deadline = Math.min(hardDeadline, Date.now() + CHAT_JOB_LIMIT_MS)" in poll
