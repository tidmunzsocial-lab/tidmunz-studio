from pathlib import Path
import re


def test_reply_timeout_cannot_be_extended_by_rate_limit_backoff():
    source = (Path(__file__).resolve().parents[1] / "snapgen_modules/chrome_ext/background.js").read_text(encoding="utf-8")
    poll = source[source.index("let deadline = Date.now() +"):source.index("async function pageSend") ]
    assert "while (Date.now() < deadline)" in poll
    assert not re.search(r"deadline\s*(?:\+=|-=|=(?!=))", poll.split(";", 1)[1])
