#!/usr/bin/env python3
"""Audit skills metadata and README generation state."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / "skills"
MANIFEST = ROOT / "skills-manifest.json"
README = ROOT / "README.md"
GENERATOR = ROOT / "scripts" / "generate-readme.py"

VALID_TYPES = {"custom", "github", "web", "third-party", "internal", "unknown"}
VALID_UPDATES = {"local", "manual-diff", "script", "git-subtree", "unknown"}


def parse_frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    data: dict[str, str] = {}
    for line in parts[1].splitlines():
        if not line.strip() or line.startswith(" ") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip()
    return data


def load_manifest() -> dict[str, Any]:
    try:
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail(f"missing {MANIFEST.relative_to(ROOT)}")
    except json.JSONDecodeError as exc:
        fail(f"invalid JSON in {MANIFEST.relative_to(ROOT)}: {exc}")


def fail(message: str) -> None:
    print(f"ERROR: {message}")
    sys.exit(1)


def warn(message: str) -> None:
    print(f"WARN: {message}")


def skill_dirs() -> list[Path]:
    return sorted(
        p for p in SKILLS_DIR.iterdir()
        if p.is_dir() and not p.name.startswith(".") and (p / "SKILL.md").exists()
    )


def non_skill_dirs() -> list[Path]:
    return sorted(
        p for p in SKILLS_DIR.iterdir()
        if p.is_dir() and not p.name.startswith(".") and not (p / "SKILL.md").exists()
    )


def audit_manifest(skills: list[Path], manifest: dict[str, Any]) -> bool:
    ok = True
    if not isinstance(manifest.get("version"), int):
        print("ERROR: manifest.version must be an integer")
        ok = False
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", str(manifest.get("updated", ""))):
        print("ERROR: manifest.updated must be YYYY-MM-DD")
        ok = False

    entries = manifest.get("skills")
    if not isinstance(entries, dict):
        print("ERROR: manifest.skills must be an object")
        return False

    skill_names = {p.name for p in skills}
    manifest_names = set(entries)

    for name in sorted(skill_names - manifest_names):
        print(f"ERROR: {name} exists in skills/ but is missing from manifest")
        ok = False
    for name in sorted(manifest_names - skill_names):
        print(f"ERROR: {name} exists in manifest but has no skills/{name}/SKILL.md")
        ok = False

    for name, meta in sorted(entries.items()):
        if not isinstance(meta, dict):
            print(f"ERROR: {name}: manifest entry must be an object")
            ok = False
            continue
        for key in ["type", "source", "update", "notes"]:
            if key not in meta:
                print(f"ERROR: {name}: missing manifest field {key}")
                ok = False
        if meta.get("type") not in VALID_TYPES:
            print(f"ERROR: {name}: invalid type {meta.get('type')!r}")
            ok = False
        if meta.get("update") not in VALID_UPDATES:
            print(f"ERROR: {name}: invalid update {meta.get('update')!r}")
            ok = False
        source = meta.get("source")
        if source is not None and not isinstance(source, str):
            print(f"ERROR: {name}: source must be string or null")
            ok = False
        if meta.get("type") in {"github", "web"} and not source:
            print(f"ERROR: {name}: {meta.get('type')} entries should include source")
            ok = False
        if not str(meta.get("notes", "")).strip():
            print(f"ERROR: {name}: notes must not be empty")
            ok = False
    return ok


def audit_frontmatter(skills: list[Path]) -> bool:
    ok = True
    for skill_dir in skills:
        frontmatter = parse_frontmatter((skill_dir / "SKILL.md").read_text(encoding="utf-8", errors="ignore"))
        for key in ["name", "description"]:
            if key not in frontmatter:
                print(f"ERROR: {skill_dir.name}: SKILL.md missing frontmatter field {key}")
                ok = False
    return ok


def audit_readme_is_current() -> bool:
    before = README.read_text(encoding="utf-8")
    subprocess.run([sys.executable, str(GENERATOR)], cwd=str(ROOT), check=True)
    after = README.read_text(encoding="utf-8")
    if before != after:
        print("ERROR: README skill table was stale; re-run scripts/generate-readme.py and review the diff")
        return False
    return True


def main() -> None:
    skills = skill_dirs()
    manifest = load_manifest()
    ok = True
    ok &= audit_manifest(skills, manifest)
    ok &= audit_frontmatter(skills)
    ok &= audit_readme_is_current()

    extras = non_skill_dirs()
    for path in extras:
        warn(f"skills/{path.name} has no SKILL.md and is ignored")

    print(f"Checked {len(skills)} skills.")
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
