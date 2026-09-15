"""Immutable progressive skill loading."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml


def load_skill(root: Path, name: str) -> tuple[dict[str, Any], str, str]:
    path = (root / "skills" / name / "SKILL.md").resolve()
    expected_root = (root / "skills").resolve()
    if not path.is_relative_to(expected_root) or not path.is_file():
        raise FileNotFoundError(name)
    content = path.read_text(encoding="utf-8")
    if not content.startswith("---\n"):
        raise ValueError(f"{name} has no front matter")
    _, raw, _ = content.split("---", 2)
    metadata = yaml.safe_load(raw)
    if metadata.get("name") != name:
        raise ValueError("skill name mismatch")
    digest = f"sha256:{hashlib.sha256(content.encode()).hexdigest()}"
    return metadata, digest, str(path.relative_to(root))
