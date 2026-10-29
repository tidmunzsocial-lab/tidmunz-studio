"""Persistence for the SnapGen.org image gateway credential."""
from __future__ import annotations

import json
from pathlib import Path


def current_image_api_key(*environments: dict) -> str:
    """Return the live image-gateway key; never fall back to the legacy video key."""
    for environment in environments:
        try:
            keyvar = environment.get("snapgen_image_api_key_var")
            value = str(keyvar.get() if keyvar is not None and hasattr(keyvar, "get") else "").strip()
        except Exception:
            value = ""
        if value:
            return value
    return ""


def load_image_api_key(path: str | Path) -> str:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    return str(data.get("api_key") or "").strip() if isinstance(data, dict) else ""


def save_image_api_key(path: str | Path, value: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    payload = {"api_key": str(value or "").strip()}
    temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    temporary.replace(target)
