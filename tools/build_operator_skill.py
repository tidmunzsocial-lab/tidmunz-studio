"""Build a portable, secret-free Tidmunz operator skill ZIP from canonical Git source."""
from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / ".agents" / "skills" / "tidmunz-remote-operator"
OUTPUT = ROOT / "tools" / "release" / "tidmunz-operator-skill.zip"


def build_skill_archive(output=OUTPUT):
    """Package only public Markdown instructions, not credentials, logs, or user data."""
    if not (SKILL / "SKILL.md").is_file():
        raise FileNotFoundError("tidmunz-remote-operator/SKILL.md is missing")
    files = sorted(p for p in SKILL.rglob("*.md") if p.is_file())
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, arcname=(Path(SKILL.name) / path.relative_to(SKILL)).as_posix())
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("skill archive is corrupted")
    return output


if __name__ == "__main__":
    result = build_skill_archive()
    print(f"{result.name}: sha256={hashlib.sha256(result.read_bytes()).hexdigest()}")
