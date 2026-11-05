"""Isolated GPT timeout regression: no Chrome login or paid video submission."""
import ast
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PY_SOURCE = ROOT / "snapgen_modules" / "snapgen_page_narrate.py"
EXT_SOURCE = ROOT / "snapgen_modules" / "chrome_ext" / "background.js"


def load_function(name, namespace):
    module = ast.parse(PY_SOURCE.read_text(encoding="utf-8"))
    node = next(n for n in ast.walk(module)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                and n.name == name)
    isolated = ast.Module(body=[node], type_ignores=[])
    exec(compile(isolated, str(PY_SOURCE), "exec"), namespace)
    return namespace[name]


class ChatTimeoutRecoveryContract(unittest.TestCase):
    def test_chat_timeout_is_bounded_but_image_generation_retains_limit(self):
        code = EXT_SOURCE.read_text(encoding="utf-8")
        self.assertIn("const CHAT_JOB_LIMIT_MS = 3 * 60 * 1000;", code)
        self.assertIn('job.type === "chat" ? CHAT_JOB_LIMIT_MS : JOB_LIMIT_MS', code)
        self.assertIn('const JOB_LIMIT_MS = 12 * 60 * 1000;', code)
        self.assertIn("ChatGPT response timed out after 3 minutes", code)
        self.assertIn("original prompt may have been sent; do not resend", code)

    def test_new_chrome_timeout_is_recognized_as_terminal(self):
        fn = load_function("gpt_relay_timed_out", {})
        self.assertTrue(fn("Bridge HTTP 502: ChatGPT response timed out after 3 minutes"))
        self.assertTrue(fn("Bridge HTTP 502: ChatGPT took longer than 12 minutes"))
        self.assertFalse(fn("rate limited 429: retry later"))

    def test_existing_video_prompts_avoid_a_second_gpt_send(self):
        log = []
        state = {"project": {"scenes": [
            {"video_prompt": "planned first shot", "seen": ""},
            {"video_prompt": "planned second shot", "seen": ""},
        ]}}
        scope = {
            "state": state, "video_mode": True,
            "log": log.append, "check_stop": lambda: None,
            "gpt_relay_timed_out": lambda err:
                "chatgpt response timed out after 3 minutes" in str(err).lower(),
            "ask_on_ui": lambda *args: self.fail("should not request a second GPT send"),
            "Stopped": RuntimeError,
        }
        fallback = load_function("use_planned_motion", scope)
        self.assertTrue(fallback([0, 1], "ChatGPT response timed out after 3 minutes"))
        self.assertTrue(state["motion_planned_only"])
        self.assertTrue(state["motion_text_only"])
        self.assertEqual(state["project"]["scenes"][0]["seen"], "")
        self.assertTrue(log)
        self.assertTrue(fallback([0, 1], "no assistant text came back"))


if __name__ == "__main__":
    unittest.main()
