#!/usr/bin/env python3
"""Update the generated skills table in README.md.

The table is built from skills/*/SKILL.md frontmatter plus skills-manifest.json.
Only the block between SKILLS_TABLE_START and SKILLS_TABLE_END is replaced.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
SKILLS_DIR = ROOT / "skills"
MANIFEST = ROOT / "skills-manifest.json"

START = "<!-- SKILLS_TABLE_START -->"
END = "<!-- SKILLS_TABLE_END -->"

TYPE_LABELS = {
    "custom": "自制",
    "github": "GitHub",
    "web": "网上",
    "third-party": "第三方",
    "internal": "内部",
    "unknown": "待确认",
}

UPDATE_LABELS = {
    "local": "本地维护",
    "manual-diff": "手动 diff 同步",
    "script": "脚本同步",
    "git-subtree": "git subtree",
    "unknown": "待确认",
}


def load_manifest() -> dict[str, Any]:
    if not MANIFEST.exists():
        return {"skills": {}}
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def parse_frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}

    data: dict[str, str] = {}
    current_key: str | None = None
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_key, current_lines
        if current_key is not None:
            value = " ".join(line.strip() for line in current_lines).strip()
            data[current_key] = clean_scalar(value)
        current_key = None
        current_lines = []

    for raw_line in parts[1].splitlines():
        if not raw_line.strip():
            continue
        if raw_line.startswith(" ") and current_key:
            current_lines.append(raw_line)
            continue
        flush()
        if ":" not in raw_line:
            continue
        key, value = raw_line.split(":", 1)
        current_key = key.strip()
        value = value.strip()
        if value in {">", ">-", "|", "|-"}:
            current_lines = []
        else:
            current_lines = [value]
    flush()
    return data


def clean_scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1]
    value = re.sub(r"\s+", " ", value).strip()
    return value


def shorten(text: str, limit: int = 96) -> str:
    text = clean_scalar(text)
    if not text:
        return "—"
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def md_escape(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def source_cell(meta: dict[str, Any]) -> str:
    source_type = meta.get("type", "unknown")
    label = TYPE_LABELS.get(source_type, source_type)
    source = meta.get("source")
    if source:
        return f"[{label}]({source})"
    return label


def update_cell(meta: dict[str, Any]) -> str:
    update = meta.get("update", "unknown")
    return UPDATE_LABELS.get(update, update)


def collect_skills() -> list[dict[str, str]]:
    manifest = load_manifest().get("skills", {})
    rows: list[dict[str, str]] = []

    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir() or skill_dir.name.startswith("."):
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue
        frontmatter = parse_frontmatter(skill_md.read_text(encoding="utf-8", errors="ignore"))
        meta = manifest.get(skill_dir.name, {})
        rows.append(
            {
                "skill": skill_dir.name,
                "name": frontmatter.get("name", skill_dir.name),
                "description": shorten(frontmatter.get("description", "")),
                "source": source_cell(meta),
                "update": update_cell(meta),
            }
        )
    return rows


def build_table() -> str:
    rows = collect_skills()
    lines = [
        "| Skill | 描述 | 来源 | 更新策略 |",
        "|---|---|---|---|",
    ]
    for row in rows:
        skill = row["skill"]
        lines.append(
            "| "
            f"[{md_escape(skill)}](skills/{skill}/) | "
            f"{md_escape(row['description'])} | "
            f"{row['source']} | "
            f"{md_escape(row['update'])} |"
        )
    return "\n".join(lines)


def update_readme() -> None:
    readme = README.read_text(encoding="utf-8")
    if START not in readme or END not in readme:
        raise SystemExit(f"README.md must contain {START} and {END} markers")
    replacement = f"{START}\n{build_table()}\n{END}"
    readme = re.sub(
        rf"{re.escape(START)}.*?{re.escape(END)}",
        replacement,
        readme,
        flags=re.S,
    )
    README.write_text(readme, encoding="utf-8")


if __name__ == "__main__":
    update_readme()
