"""Bounded JSON/CLI adapter for ChatGPT's connected Tidmunz Studio operator.

Only the local Windows app actually starts/runs paid media jobs. This adapter
provides sanitized observations and explicit, receipt-aware actions. It never
prints the Mobile Web access token or remote public URL.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone

LOCAL = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
APP = LOCAL / "Tidmunz Studio"
DATA = APP / "snapgen_data"
STORIES = APP / "export" / "วิดีโอออโต้"
JOURNAL = DATA / "logs" / "tidmunz_operator_last_command.json"
WATCH = DATA / "logs" / "tidmunz_operator_watch.json"


class OperatorError(RuntimeError):
    pass


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def endpoint(path):
    source = (DATA / "mobile_web_url.txt").read_text(encoding="utf-8").strip()
    parsed = urllib.parse.urlsplit(source)
    if not parsed.query:
        raise OperatorError("No local app authorization is configured")
    # The credential remains entirely on the device and never enters stdout.
    return f"http://127.0.0.1:8765{path}?{parsed.query}"


def request(path, data=None):
    try:
        raw = None if data is None else json.dumps(data, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(endpoint(path), data=raw,
                                     headers={"Content-Type": "application/json"} if raw else {},
                                     method="POST" if raw is not None else "GET")
        with urllib.request.urlopen(req, timeout=12) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8", errors="replace"))
            error = str(payload.get("error") or "command rejected")
        except (ValueError, AttributeError):
            error = "command rejected"
        raise OperatorError(f"Local app HTTP {exc.code}: {error[:180]}") from None
    except (OSError, TimeoutError) as exc:
        raise OperatorError(f"Local app unavailable or response uncertain ({type(exc).__name__})") from None


def project_for(title):
    if not title or any(part in title for part in ("..", "/", "\\", "\0")):
        return None
    source = (STORIES / title / "project.json").resolve()
    if not source.is_relative_to(STORIES.resolve()) or not source.is_file():
        return None
    try:
        data = json.loads(source.read_text(encoding="utf-8-sig"))
    except (ValueError, OSError):
        return None
    return data if isinstance(data, dict) else None


def clip_exists(path):
    if not path:
        return False
    try:
        source = Path(str(path))
        return source.is_file() and source.stat().st_size > 4096
    except (OSError, ValueError):
        return False


def summarize(status):
    auto = status.get("auto") or {}
    shots = auto.get("shots") or []
    title = str(auto.get("title") or "")
    data = project_for(title)
    scenes = (data or {}).get("scenes") or []
    if scenes:
        clips = sum(clip_exists(sc.get("clip")) for sc in scenes)
        images = sum(bool(sc.get("image")) and Path(str(sc["image"])).is_file() for sc in scenes)
        first_missing = next((i + 1 for i, sc in enumerate(scenes)
                              if not clip_exists(sc.get("clip"))), None)
    else:
        clips = sum(bool(s.get("clip")) for s in shots)
        images = sum(bool(s.get("image")) for s in shots)
        first_missing = next((i + 1 for i, s in enumerate(shots) if not s.get("clip")), None)
    next_scene = scenes[first_missing - 1] if first_missing and scenes else {}
    error = str(next_scene.get("clip_error") or next_scene.get("error") or "")[:200]
    has_receipt = any(bool(next_scene.get(key)) for key in (
        "clip_task_id", "clip_job_id", "clip_uuid", "clip_receipt",
        "clip_request_id", "video_task_id", "provider_task_id"))
    statuses = [str(slot.get("status") or "") for slot in (status.get("slots") or [])]
    final_path = str((data or {}).get("last_video") or "")
    final_ready = bool(data and (data.get("done") or {}).get("video")
                       and first_missing is None and clip_exists(final_path))
    return {
        "observed_at": now(), "app_ready": bool(status.get("ready")),
        "story": title, "auto_busy": bool(auto.get("busy")),
        "stage": str(auto.get("stage") or "")[:190],
        "detail": str(auto.get("detail") or "")[:220],
        "percent_ui": auto.get("percent"), "images": images, "clips": clips,
        "total": len(scenes) or len(shots), "next_missing_shot": first_missing,
        "next_shot_error": error, "next_shot_has_provider_receipt": has_receipt,
        "slots": statuses, "final_ready": final_ready,
        "final_file": final_path if final_ready else "",
    }


def diagnose(s):
    if not s["app_ready"]:
        return {"diagnosis": "app_starting", "reason": "Local app is not ready"}
    if s["final_ready"]:
        return {"diagnosis": "complete", "reason": "All scene clips and final movie file exist"}
    if s["auto_busy"]:
        return {"diagnosis": "working", "reason": s["detail"] or s["stage"]}
    error = s["next_shot_error"].lower()
    if s["next_shot_has_provider_receipt"]:
        return {"diagnosis": "provider_task_may_be_pending", "reason":
                "A provider receipt exists; verify its final state before a paid retry"}
    if any(term in error for term in ("timeout", "timed out", "http 502", "http 504", "unknown", "pending")):
        return {"diagnosis": "ambiguous_cloud_result", "reason":
                "Previous provider request may have been accepted; do not resubmit blindly"}
    if any(term in error for term in ("traffic", "too many", "429", "rate limit", "ลิมิต", "คิวเต็ม")):
        return {"diagnosis": "provider_capacity", "reason":
                "Provider limited service; inspect cooldown and receipts before resuming"}
    if s["total"] and s["clips"] < s["total"]:
        return {"diagnosis": "paused_incomplete", "reason":
                f"{s['total']-s['clips']} clips are missing; resume requires explicit paid-work authorization"}
    return {"diagnosis": "idle", "reason": "No active generation recorded"}


def save_journal(value):
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    tmp = JOURNAL.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, JOURNAL)


def previous_command():
    try:
        return json.loads(JOURNAL.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def execute(action, data=None):
    old = previous_command()
    if old.get("status") in ("submitted", "pending", "unknown"):
        # Poll once using the SAME id, even if previous call timed out.
        old_id = old.get("id")
        if not old_id:
            raise OperatorError("An unresolved prior command exists; review journal")
        try:
            receipt = request("/api/receipt/" + old_id)
            if receipt.get("pending"):
                raise OperatorError("Previous command is still pending; do not submit another")
            if receipt.get("ok") is False and "ไม่มีผลตอบรับ" in str(receipt.get("error") or ""):
                raise OperatorError("Prior command receipt unavailable after restart; manual review required")
            old["status"] = "done" if receipt.get("ok") else "rejected"
            old["result"] = str(receipt.get("message") or receipt.get("error") or "")[:170]
            save_journal(old)
        except OperatorError:
            raise
    command_id = "tidmunz-ai-" + uuid.uuid4().hex
    entry = {"id": command_id, "action": action, "status": "submitted", "timestamp": now(),
             "project": str(data.get("name") or "") if data else ""}
    save_journal(entry)
    try:
        reply = request("/api/command", {"id": command_id, "action": action, "data": data or {}})
    except OperatorError:
        entry["status"] = "unknown"
        save_journal(entry)
        raise
    if reply.get("pending"):
        entry["status"] = "pending"
        save_journal(entry)
        return {"accepted": "pending", "request_id": command_id}
    entry["status"] = "done" if reply.get("ok") else "rejected"
    entry["result"] = str(reply.get("message") or reply.get("error") or "")[:170]
    save_journal(entry)
    return {"accepted": bool(reply.get("ok")), "request_id": command_id, "message": entry["result"]}


def handle(args):
    if args.command == "projects":
        items = []
        if STORIES.is_dir():
            for path in sorted(STORIES.glob("*/project.json"),
                               key=lambda item: item.stat().st_mtime, reverse=True)[:30]:
                data = project_for(path.parent.name)
                if data:
                    scenes = data.get("scenes") or []
                    items.append({"title": path.parent.name, "total": len(scenes),
                                  "clips": sum(clip_exists(sc.get("clip")) for sc in scenes)})
        return {"projects": items}
    s = summarize(request("/api/status"))
    if args.command == "status":
        return s
    if args.command == "diagnose":
        return {"status": s, **diagnose(s)}
    if args.command == "stop":
        if not s["auto_busy"]:
            return {"status": s, "note": "Already idle; no command sent"}
        return execute("auto_stop")
    if args.command == "open":
        if s["auto_busy"]:
            raise OperatorError("Cannot switch projects while Auto is running")
        if not project_for(args.title):
            raise OperatorError("That exact existing project cannot be found")
        if args.title == s["story"]:
            return {"status": s, "note": "Already open"}
        return execute("auto_open", {"name": args.title})
    if args.command == "resume":
        if not args.authorize_paid:
            raise OperatorError("Paid Auto resume needs explicit user authorization (--authorize-paid)")
        if not s["story"] or not s["total"]:
            raise OperatorError("Open an existing story first")
        if s["auto_busy"]:
            return {"status": s, "note": "Already running; did not submit a second job"}
        if any(slot not in ("Idle", "ว่าง", "", "พร้อม") for slot in s["slots"]):
            raise OperatorError("Another video slot is active or uncertain")
        classification = diagnose(s)["diagnosis"]
        if classification in ("provider_task_may_be_pending", "ambiguous_cloud_result", "provider_capacity"):
            raise OperatorError(f"{classification}: inspect provider receipts before retry")
        return execute("auto_start")
    raise OperatorError("Unsupported command")


def watch(interval):
    while True:
        try:
            status = summarize(request("/api/status"))
            status.update(diagnose(status))
        except (OperatorError, OSError, ValueError) as exc:
            status = {"observed_at": now(), "diagnosis": "local_app_unavailable",
                      "reason": type(exc).__name__}
        WATCH.parent.mkdir(parents=True, exist_ok=True)
        tmp = WATCH.with_suffix(".tmp")
        tmp.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, WATCH)
        if status.get("final_ready"):
            return
        time.sleep(max(10, interval))


def main():
    parser = argparse.ArgumentParser(description="Tidmunz Studio local AI operator")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("projects", "status", "diagnose", "stop"):
        sub.add_parser(name)
    opener = sub.add_parser("open")
    opener.add_argument("--title", required=True)
    starter = sub.add_parser("resume")
    starter.add_argument("--authorize-paid", action="store_true")
    monitor = sub.add_parser("watch")
    monitor.add_argument("--interval", type=int, default=15)
    args = parser.parse_args()
    try:
        if args.command == "watch":
            watch(args.interval)
            return 0
        print(json.dumps(handle(args), ensure_ascii=False, indent=2))
        return 0
    except (OperatorError, OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)[:260]}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
