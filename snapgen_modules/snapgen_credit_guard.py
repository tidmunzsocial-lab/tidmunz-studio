"""Per-image SnapGen billing and persistent consent; never attribute batch deltas."""
import math
import json

IMAGE_CREDIT_LIMIT = 10.0


def image_response_items(response):
    """Yield SSE/NDJSON metadata immediately, while retaining pretty JSON support."""
    buffered = []
    for raw in response:
        text = raw.decode("utf-8", "replace").strip()
        if not text or text == "[DONE]" or text.startswith((":", "event:", "id:", "retry:")):
            continue
        if text.startswith("data:"):
            text = text[5:].strip()
        if not text or text == "[DONE]":
            continue
        if buffered:
            buffered.append(text)
            continue
        try:
            value = json.loads(text)
        except ValueError:
            buffered.append(text)
        else:
            yield value
    if buffered:
        yield json.loads("\n".join(buffered))


def image_billing(payload, task_id=None):
    if not isinstance(payload, dict):
        return {"task_id": task_id, "used_credit": None}
    task_id = next((payload.get(k) for k in ("uuid", "history_uuid", "conversion_uuid", "id")
                    if payload.get(k)), task_id)
    raw = payload.get("used_credit")
    try:
        credit = float(raw) if raw is not None and not isinstance(raw, bool) else None
    except (TypeError, ValueError):
        credit = None
    if credit is not None and (not math.isfinite(credit) or credit < 0):
        credit = None
    if credit is None:
        for key in ("data", "history", "result"):
            child = payload.get(key)
            if isinstance(child, dict):
                found = image_billing(child, task_id)
                task_id = found["task_id"]
                if found["used_credit"] is not None:
                    return found
    return {"task_id": str(task_id) if task_id is not None else None, "used_credit": credit}


def record_image_billing(project, name, record):
    credit = record.get("used_credit")
    item = {"name": name, "task_id": record.get("task_id"), "used_credit": credit}
    project.setdefault("snapgen_image_charges", {})[str(record.get("task_id") or name)] = item
    baseline = project.get("snapgen_image_credit_baseline")
    if credit is not None and 0 < credit <= IMAGE_CREDIT_LIMIT and baseline is None:
        project["snapgen_image_credit_baseline"] = credit
    previous = project.get("snapgen_credit_warning")
    if credit is not None and credit > IMAGE_CREDIT_LIMIT:
        if not previous or previous.get("used_credit") is None or credit > previous["used_credit"]:
            project["snapgen_credit_warning"] = dict(item, baseline=baseline)
    elif credit is None:
        project["snapgen_credit_warning"] = dict(previous or dict(item, baseline=None),
                                                  unverified=True, unknown_name=name)
    return project.get("snapgen_credit_warning")


def credit_consent_required(project, acceptance=None):
    warning = project.get("snapgen_credit_warning")
    if not warning:
        return False
    acceptance = acceptance or {}
    if warning.get("unverified") and not acceptance.get("allow_unknown", False):
        return True
    cost = warning.get("used_credit")
    if cost is None:
        return not acceptance.get("allow_unknown", False)
    return float(acceptance.get("ceiling") or 0) < cost


def credit_warning_text(warning):
    if not warning:
        return ""
    name, credit = warning.get("name", "รูป"), warning.get("used_credit")
    if credit is None or warning.get("unverified"):
        known = f" (ก่อนหน้านี้เคยหัก {credit:g} เครดิต/รูป)" if credit is not None else ""
        return (f"⚠ SnapGen {warning.get('unknown_name') or name}: ยังยืนยันเครดิตต่อรูปจาก History ไม่ได้{known} "
                "พักคำขอใหม่ — ต้องยอมรับความเสี่ยงหรือเปลี่ยนเป็น GPT Chrome")
    baseline = warning.get("baseline")
    ratio = (f" · เป็น {credit / baseline:g} เท่าของราคาที่เคยวัด {baseline:g} เครดิต"
             if baseline and baseline > 0 else "")
    return (f"⚠ SnapGen {name}: หัก {credit:g} เครดิต/รูป เกินเกณฑ์ {IMAGE_CREDIT_LIMIT:g} เครดิต"
            f"{ratio} — พักคำขอใหม่ ต้องยอมรับราคาหรือเปลี่ยนเป็น GPT Chrome")
