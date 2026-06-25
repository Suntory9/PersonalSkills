#!/usr/bin/env python3
"""localagentskills — 跨平台 CLI (macOS / Linux / Windows)

管理 Claude Code / Codex 本地 skills 的命令行工具。

用法:
  python3 install.py list                     # 列出可用技能
  python3 install.py install [skill ...]      # 安装到当前项目
  python3 install.py install --global         # 全局安装全部技能
  python3 install.py uninstall [skill ...]    # 卸载当前项目中的技能
  python3 install.py status                   # 查看全局安装状态
  python3 install.py update                   # 更新仓库和在线 skill 内容
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import shutil
import stat
import tempfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

# ── 可选依赖 ────────────────────────────────────────────────────

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    from rich import box
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

try:
    from InquirerPy import inquirer
    from InquirerPy.base.control import Choice
    INQUIRER_AVAILABLE = True
except ImportError:
    INQUIRER_AVAILABLE = False


# ── 跨平台常量 ────────────────────────────────────────────────

REPO_DIR = Path(__file__).resolve().parent
SKILLS_DIR = REPO_DIR / "skills"
MANIFEST = REPO_DIR / "skills-manifest.json"
SCHEMA = REPO_DIR / "skills-manifest.schema.json"

# Claude Code / Codex 技能目录
CLAUDE_SKILLS = Path.home() / ".claude" / "skills"
CODEX_SKILLS = Path.home() / ".codex" / "skills"

# ANSI 颜色（Windows 10+ 终端均支持）
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
CYAN = "\033[0;36m"
RED = "\033[0;31m"
DIM = "\033[2m"
BOLD = "\033[1m"
NC = "\033[0m"  # reset


# ── Rich 输出封装 ──────────────────────────────────────────────

_console: Console | None = None


def get_console(no_color: bool = False) -> Console:
    """获取 Rich Console 实例。"""
    global _console
    if _console is None:
        if RICH_AVAILABLE:
            _console = Console(no_color=no_color)
        else:
            _console = Console(force_terminal=False, no_color=True) if RICH_AVAILABLE else None  # type: ignore[assignment]
    return _console  # type: ignore[return-value]


def _is_json_mode() -> bool:
    """检查当前是否处于 JSON 输出模式。用环境变量传递。"""
    return os.environ.get("LOCALAGENTSKILLS_JSON", "") == "1"


def print_success(message: str) -> None:
    """输出成功消息。"""
    if _is_json_mode():
        return
    if RICH_AVAILABLE:
        get_console().print(f"[green]✓[/green] {message}")
    else:
        print(f"{GREEN}✓{NC} {message}")


def print_warning(message: str) -> None:
    """输出警告消息。"""
    if _is_json_mode():
        return
    if RICH_AVAILABLE:
        get_console().print(f"[yellow]![/yellow] {message}")
    else:
        print(f"{YELLOW}!{NC} {message}")


def print_error(message: str) -> None:
    """输出错误消息。"""
    if _is_json_mode():
        print(message, file=sys.stderr)
        return
    if RICH_AVAILABLE:
        get_console().print(f"[red]✗[/red] {message}")
    else:
        print(f"{RED}✗{NC} {message}")


def print_table(
    title: str,
    columns: list[str],
    rows: list[list[str]],
    no_color: bool = False,
) -> None:
    """输出 Rich 表格；Rich 不可用时回退到简单文本。"""
    if _is_json_mode():
        return
    if RICH_AVAILABLE:
        console = get_console(no_color)
        table = Table(title=title, box=box.HEAVY_HEAD)
        for col in columns:
            table.add_column(col, no_wrap=False)
        for row in rows:
            table.add_row(*[str(c) for c in row])
        console.print(table)
    else:
        # 简单文本回退
        print(f"\n{title}")
        print("-" * 60)
        col_widths = [max(len(str(row[i])) for row in rows + [columns]) for i in range(len(columns))]
        header = "  ".join(f"{columns[i]:<{col_widths[i]}}" for i in range(len(columns)))
        print(f"  {header}")
        print(f"  {'-' * (sum(col_widths) + 2 * (len(columns) - 1))}")
        for row in rows:
            line = "  ".join(f"{str(row[i]):<{col_widths[i]}}" for i in range(len(columns)))
            print(f"  {line}")
        print()


# ── 辅助函数 ──────────────────────────────────────────────────

def _can_symlink() -> bool:
    """检测当前平台是否支持符号链接。"""
    if sys.platform != "win32":
        return True
    # Windows: 需要管理员权限或开发者模式
    try:
        test_src = SKILLS_DIR / ".symlink_test_src"
        test_dst = SKILLS_DIR / ".symlink_test_dst"
        test_src.mkdir(parents=True, exist_ok=True)
        os.symlink(str(test_src), str(test_dst))
        test_dst.unlink()
        test_src.rmdir()
        return True
    except OSError:
        return False


CAN_SYMLINK: bool = _can_symlink()


def link_or_copy(src: Path, dst: Path) -> str:
    """创建符号链接；Windows 无权限时回退到复制。

    返回操作类型: "linked" / "copied" / "junction"
    """
    if CAN_SYMLINK:
        os.symlink(str(src), str(dst), target_is_directory=src.is_dir())
        return "linked"
    elif sys.platform == "win32":
        # 尝试 junction (仅目录、仅 NTFS)
        try:
            import _winapi
            _winapi.CreateJunction(str(src), str(dst))
            return "junction"
        except (OSError, ImportError, AttributeError):
            pass
        # 最后手段：复制
        shutil.copytree(str(src), str(dst))
        return "copied (fallback — symlink not available)"
    else:
        shutil.copytree(str(src), str(dst))
        return "copied (fallback)"


def is_symlink_or_junction(path: Path) -> bool:
    """判断 path 是否为符号链接或 Windows junction。"""
    if path.is_symlink():
        return True
    if sys.platform == "win32":
        try:
            attrs = path.lstat().st_file_attributes
            return bool(attrs & stat.FILE_ATTRIBUTE_REPARSE_POINT)
        except (AttributeError, OSError):
            return False
    return False


def read_symlink_target(path: Path) -> str | None:
    """读取符号链接目标（跨平台）。"""
    try:
        return os.readlink(str(path))
    except OSError:
        return None


def project_skill_present(path: Path) -> bool:
    """Return True when a project skill entry exists, including broken symlinks."""
    return path.exists() or path.is_symlink() or is_symlink_or_junction(path)


def remove_link_or_junction(path: Path) -> None:
    """删除符号链接或 Windows junction，不递归删除真实目标。"""
    if path.is_symlink():
        path.unlink()
    elif path.is_dir():
        path.rmdir()
    else:
        path.unlink()


def pip_install(req_path: Path) -> bool:
    """pip install -r requirements.txt，成功返回 True。"""
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-q", "-r", str(req_path)],
            check=True, capture_output=True, text=True,
        )
        return True
    except subprocess.CalledProcessError:
        return False


def read_description(skill_dir: Path) -> str:
    """从 SKILL.md frontmatter 中读取 description。"""
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        return ""
    try:
        text = skill_md.read_text(encoding="utf-8")
        lines = text.splitlines()
        in_front = False
        for index, line in enumerate(lines):
            if line.strip() == "---":
                if not in_front:
                    in_front = True
                    continue
                else:
                    break
            if in_front and line.startswith("description:"):
                value = line.split(":", 1)[1].strip()
                if value in {">", ">-", "|", "|-"}:
                    parts = []
                    for follow in lines[index + 1:]:
                        if follow.strip() == "---" or (follow and not follow.startswith((" ", "\t"))):
                            break
                        stripped = follow.strip()
                        if stripped:
                            parts.append(stripped)
                    value = " ".join(parts)
                value = value.strip().strip("\"'")
                return " ".join(value.split())
    except Exception:
        pass
    return ""


# ── 结构化数据 ──────────────────────────────────────────────────

@dataclass
class OperationResult:
    """安装/卸载操作的结构化结果。"""
    added: list[str] = field(default_factory=list)
    already: list[str] = field(default_factory=list)
    replaced: list[str] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)  # (name, reason)
    removed: list[str] = field(default_factory=list)
    not_installed: list[str] = field(default_factory=list)
    errors: list[tuple[str, str]] = field(default_factory=list)  # (name, error)
    project_setup: list[str] = field(default_factory=list)


def collect_skills() -> list[dict[str, Any]]:
    """返回所有 skill 的结构化信息，方便 JSON 和表格共用。"""
    if not SKILLS_DIR.is_dir():
        return []

    manifest = load_skills_manifest().get("skills", {})
    skills = []
    for d in sorted(SKILLS_DIR.iterdir()):
        if d.is_dir() and (d / "SKILL.md").is_file():
            meta = manifest.get(d.name, {})
            skills.append({
                "name": d.name,
                "path": str(d),
                "description": read_description(d),
                "type": meta.get("type"),
                "source": meta.get("source"),
                "update": meta.get("update"),
            })
    return skills


# ── 核心逻辑 ──────────────────────────────────────────────────

def list_skills(json_output: bool = False, no_color: bool = False) -> None:
    """列出 skills/ 下所有可用技能。"""
    if not SKILLS_DIR.is_dir():
        if json_output:
            print(json.dumps({"skills": []}))
        else:
            print_warning("No skills directory found.")
        return

    data = collect_skills()

    if json_output:
        output = {
            "skills": [
                {
                    "name": s["name"],
                    "description": s["description"],
                    "type": s["type"],
                    "source": s["source"],
                    "update": s["update"],
                }
                for s in data
            ]
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return

    # Rich 表格输出
    type_labels: dict[str, str] = {
        "github": "GitHub",
        "custom": "custom",
        "web": "web",
        "internal": "internal",
        "third-party": "third-party",
    }
    update_labels: dict[str, str] = {
        "script": "script",
        "local": "local",
        "manual-diff": "manual diff",
        "git-subtree": "git subtree",
    }

    rows = []
    for s in data:
        type_str = type_labels.get(s["type"] or "", s["type"] or "-")
        update_str = update_labels.get(s["update"] or "", s["update"] or "-")
        rows.append([s["name"], type_str, update_str, s["description"]])

    print_table(
        "Available Skills",
        ["Skill", "Source", "Update", "Description"],
        rows,
        no_color=no_color,
    )


def select_skills(names: list[str] | None = None) -> list[Path]:
    """返回选中的技能目录列表。names=None 表示全部。"""
    if not SKILLS_DIR.is_dir():
        return []
    if names:
        selected = []
        for name in names:
            d = SKILLS_DIR / name
            if d.is_dir() and (d / "SKILL.md").is_file():
                selected.append(d)
            else:
                print_error(f"Skill not found: {name}")
                sys.exit(1)
        return selected
    return [d for d in sorted(SKILLS_DIR.iterdir())
            if d.is_dir() and (d / "SKILL.md").is_file()]


def shorten(text: str, limit: int = 58) -> str:
    """压缩描述文本，便于选择列表展示。"""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[:limit].rfind(" ")
    return text[:cut if cut > 20 else limit].rstrip() + "..."


def parse_selection(selection: str, max_index: int) -> list[int]:
    """解析 1 3 5 或 1-4 这样的编号选择。"""
    indexes: list[int] = []
    for part in selection.replace(",", " ").split():
        if "-" in part:
            start_text, end_text = part.split("-", 1)
            if not start_text.isdigit() or not end_text.isdigit():
                continue
            start, end = int(start_text), int(end_text)
            if start > end:
                start, end = end, start
            indexes.extend(range(start - 1, end))
        elif part.isdigit():
            indexes.append(int(part) - 1)
    return sorted({i for i in indexes if 0 <= i < max_index})


def read_interactive_key() -> str:
    """读取一个交互按键，归一化为 up/down/space/enter/escape。"""
    if sys.platform == "win32":
        import msvcrt

        char = msvcrt.getwch()
        if char in ("\x00", "\xe0"):
            key = msvcrt.getwch()
            return {"H": "up", "P": "down"}.get(key, "")
        return {
            "\r": "enter",
            " ": "space",
            "\x1b": "escape",
            "\x01": "all",
            "j": "down",
            "k": "up",
        }.get(char.lower(), char.lower())

    import termios
    import tty

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        char = sys.stdin.read(1)
        if char == "\x1b":
            rest = sys.stdin.read(2)
            if rest == "[A":
                return "up"
            if rest == "[B":
                return "down"
            return "escape"
        return {
            "\r": "enter",
            "\n": "enter",
            " ": "space",
            "\x01": "all",
            "j": "down",
            "k": "up",
        }.get(char.lower(), char.lower())
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def choose_project_skills_numbered(skills: list[Path], agents_dir: Path, project_dir: Path) -> list[Path]:
    """非 TTY 环境下的编号选择 fallback。"""
    print(f"{CYAN}Target project:{NC} {BOLD}{project_dir}{NC}")
    print(f"{CYAN}Available skills:{NC}\n")
    for index, skill_dir in enumerate(skills, start=1):
        mark = f"{GREEN}✓{NC}" if project_skill_present(agents_dir / skill_dir.name) else " "
        desc = shorten(read_description(skill_dir))
        print(f"  {YELLOW}{index:2d}){NC} {mark} {BOLD}{skill_dir.name:<36}{NC} {DIM}{desc}{NC}")

    print("")
    print(f"{CYAN}输入编号安装（如 1 3 5 或 1-4），输入 a 全选，直接回车退出：{NC}", end="")
    selection = input().strip()
    if not selection:
        return []
    if selection.lower() == "a":
        return skills
    indexes = parse_selection(selection, len(skills))
    return [skills[i] for i in indexes]


def choose_project_skills_inquirer(skills: list[Path], agents_dir: Path, project_dir: Path) -> list[Path]:
    """使用 InquirerPy 的交互式多选界面。"""
    if not INQUIRER_AVAILABLE:
        return choose_project_skills_numbered(skills, agents_dir, project_dir)

    choices = []
    for skill_dir in skills:
        name = skill_dir.name
        description = shorten(read_description(skill_dir), 50)
        installed = project_skill_present(agents_dir / name)
        display = f"{name:<36} {description}"
        if installed:
            display += " (installed)"
        choices.append(
            Choice(value=name, name=display, enabled=installed)
        )

    try:
        selected_names = inquirer.checkbox(
            message="Select skills to enable:",
            choices=choices,
            instruction="Space: toggle · Ctrl-A: all · Enter: confirm",
            vi_mode=False,
        ).execute()
    except KeyboardInterrupt:
        print()
        print_warning("Cancelled.")
        return []

    if not selected_names:
        return []

    name_to_skill = {d.name: d for d in skills}
    return [name_to_skill[n] for n in selected_names if n in name_to_skill]


def render_skill_picker(skills: list[Path], agents_dir: Path, selected: set[int], cursor: int, project_dir: Path) -> None:
    """渲染空格多选界面（旧 raw picker，作为 fallback）。"""
    print("\033[2J\033[H", end="")
    print(f"{CYAN}Target project:{NC} {BOLD}{project_dir}{NC}")
    print(f"{CYAN}选择 Skills：{NC}{DIM}↑/↓ 或 j/k 移动，Space 勾选，Ctrl-A 全选/取消，Enter 确认，Esc 退出{NC}\n")
    for index, skill_dir in enumerate(skills):
        installed = project_skill_present(agents_dir / skill_dir.name)
        pointer = f"{CYAN}>{NC}" if index == cursor else " "
        checkbox = f"{GREEN}[x]{NC}" if index in selected else "[ ]"
        installed_tag = f" {YELLOW}(installed){NC}" if installed else ""
        desc = shorten(read_description(skill_dir))
        line_style = BOLD if index == cursor else ""
        print(f"{pointer} {checkbox} {line_style}{skill_dir.name:<36}{NC}{installed_tag} {DIM}{desc}{NC}")


def choose_project_skills(project_dir: Path) -> list[Path]:
    """交互式选择要安装到项目的技能。

    优先级：InquirerPy > 旧 raw picker > 编号 fallback
    """
    skills = select_skills(None)
    agents_dir = project_dir / ".agents" / "skills"

    if not sys.stdin.isatty():
        return choose_project_skills_numbered(skills, agents_dir, project_dir)

    if INQUIRER_AVAILABLE:
        return choose_project_skills_inquirer(skills, agents_dir, project_dir)

    # 旧的 raw terminal picker 作为 fallback
    selected = {index for index, skill_dir in enumerate(skills) if project_skill_present(agents_dir / skill_dir.name)}
    cursor = 0
    while True:
        render_skill_picker(skills, agents_dir, selected, cursor, project_dir)
        key = read_interactive_key()
        if key == "up":
            cursor = (cursor - 1) % len(skills)
        elif key == "down":
            cursor = (cursor + 1) % len(skills)
        elif key == "space":
            if cursor in selected:
                selected.remove(cursor)
            else:
                selected.add(cursor)
        elif key == "all":
            selected = set() if len(selected) == len(skills) else set(range(len(skills)))
        elif key == "enter":
            print("\033[2J\033[H", end="")
            return [skills[index] for index in sorted(selected)]
        elif key == "escape":
            print("\033[2J\033[H", end="")
            return []


def target_dirs(target: str) -> list[Path]:
    """返回目标平台的技能目录列表。"""
    mapping = {
        "claude": [CLAUDE_SKILLS],
        "codex":  [CODEX_SKILLS],
        "both":   [d for d in (CLAUDE_SKILLS, CODEX_SKILLS)],
    }
    return mapping.get(target, [CLAUDE_SKILLS, CODEX_SKILLS])


def _skill_installed_in_targets(skill_name: str, targets: list[Path]) -> bool:
    """Return True if a skill is installed in any of the target directories."""
    return any(project_skill_present(target / skill_name) for target in targets)


def choose_global_install_skills(targets: list[Path]) -> list[Path]:
    """Interactively choose skills to install globally."""
    skills = select_skills(None)
    if not sys.stdin.isatty():
        print_warning("Non-interactive terminal detected. Pass skill names or use --all with --global.")
        return []

    if INQUIRER_AVAILABLE:
        choices = []
        for skill_dir in skills:
            name = skill_dir.name
            description = shorten(read_description(skill_dir), 50)
            installed = _skill_installed_in_targets(name, targets)
            display = f"{name:<36} {description}"
            if installed:
                display += " (installed globally)"
            choices.append(Choice(value=name, name=display, enabled=installed))
        try:
            selected_names = inquirer.checkbox(
                message="Select skills to install globally:",
                choices=choices,
                instruction="Space: toggle · Ctrl-A: all · Enter: confirm",
                vi_mode=False,
            ).execute()
        except KeyboardInterrupt:
            print()
            print_warning("Cancelled.")
            return []
        if not selected_names:
            return []
        name_to_skill = {d.name: d for d in skills}
        return [name_to_skill[n] for n in selected_names if n in name_to_skill]

    print(f"\n{CYAN}Available skills for global install:{NC}\n")
    for index, skill_dir in enumerate(skills, start=1):
        mark = f"{GREEN}✓{NC}" if _skill_installed_in_targets(skill_dir.name, targets) else " "
        desc = shorten(read_description(skill_dir))
        print(f"  {YELLOW}{index:2d}){NC} {mark} {BOLD}{skill_dir.name:<36}{NC} {DIM}{desc}{NC}")
    print(f"\n{CYAN}输入编号安装（如 1 3 5 或 1-4），输入 a 全选，直接回车退出：{NC}", end="")
    selection = input().strip()
    if not selection:
        return []
    if selection.lower() == "a":
        return skills
    indexes = parse_selection(selection, len(skills))
    return [skills[i] for i in indexes]


def global_installed_skill_paths(targets: list[Path]) -> list[Path]:
    """Return known skill paths currently installed in any global target."""
    available = {d.name: d for d in select_skills(None)}
    installed_names: set[str] = set()
    for target in targets:
        if not target.is_dir():
            continue
        for path in target.iterdir():
            if path.name in available:
                installed_names.add(path.name)
    return [available[name] for name in sorted(installed_names)]


def choose_global_uninstall_skills(targets: list[Path]) -> list[Path]:
    """Interactively choose globally installed skills to uninstall."""
    installed = global_installed_skill_paths(targets)
    if not installed:
        print_warning("No globally installed skills found.")
        return []
    if not sys.stdin.isatty():
        print_warning("Non-interactive terminal detected. Pass skill names or use --all with --global.")
        return []

    if INQUIRER_AVAILABLE:
        try:
            choices = [
                Choice(value=p.name, name=f"{p.name:<36} (installed globally)", enabled=False)
                for p in installed
            ]
            selected_names = inquirer.checkbox(
                message="Select global skills to uninstall:",
                choices=choices,
                instruction="Space: toggle · Ctrl-A: all · Enter: confirm",
                vi_mode=False,
            ).execute()
        except KeyboardInterrupt:
            print()
            print_warning("Cancelled.")
            return []
        if not selected_names:
            return []
        by_name = {p.name: p for p in installed}
        return [by_name[n] for n in selected_names if n in by_name]

    print(f"\n{CYAN}Globally installed skills:{NC}")
    for index, p in enumerate(installed, start=1):
        print(f"  {YELLOW}{index:2d}){NC} {BOLD}{p.name}{NC}")
    print(f"\n{CYAN}输入编号卸载（如 1 3 5 或 1-4），输入 a 全选，直接回车退出：{NC}", end="")
    selection = input().strip()
    if not selection:
        return []
    if selection.lower() == "a":
        return installed
    indexes = parse_selection(selection, len(installed))
    return [installed[i] for i in indexes]


def install_skills(skills: list[Path], targets: list[Path], do_pip: bool, force: bool = False) -> None:
    """安装技能到目标目录。"""
    # 预扫描：统计已有 skill
    pre_existing: list[str] = []
    pre_wrong_link: list[tuple[str, str]] = []
    pre_blocked: list[tuple[str, str]] = []
    for skill_dir in skills:
        name = skill_dir.name
        for target_dir in targets:
            link_path = target_dir / name
            if is_symlink_or_junction(link_path) or link_path.is_symlink():
                current = read_symlink_target(link_path)
                if current and Path(current).resolve() == skill_dir.resolve():
                    pre_existing.append(name)
                elif current:
                    pre_wrong_link.append((name, current))
            elif link_path.exists():
                pre_blocked.append((name, str(target_dir)))

    if pre_existing and not _is_json_mode():
        print(f"\n{YELLOW}ℹ  {len(set(pre_existing))} skills already installed (项目/全局中已有，保留现有):{NC}")
        for name in sorted(set(pre_existing)):
            print(f"  {DIM}- {name}{NC}")
    if pre_wrong_link and not _is_json_mode():
        print(f"\n{YELLOW}⚠  {len(pre_wrong_link)} skills linked to a different location, will be replaced:{NC}")
        for name, target in pre_wrong_link:
            print(f"  {DIM}- {name} → {target}{NC}")
    if pre_blocked and not _is_json_mode():
        print(f"\n{YELLOW}⚠  {len(pre_blocked)} skills blocked by existing non-link entries (will be skipped):{NC}")
        for name, loc in pre_blocked:
            print(f"  {DIM}- {name} (in {loc}){NC}")

    for target_dir in targets:
        target_dir.mkdir(parents=True, exist_ok=True)
        print(f"\n{CYAN}==> Installing to {target_dir}{NC}")

        for skill_dir in skills:
            name = skill_dir.name
            link_path = target_dir / name

            # 已是正确的链接 → 跳过
            if is_symlink_or_junction(link_path) or link_path.is_symlink():
                current = read_symlink_target(link_path)
                if current and Path(current).resolve() == skill_dir.resolve():
                    print(f"  {GREEN}[OK]{NC} {name} (already linked)")
                    continue
                else:
                    print(f"  {YELLOW}[WARN]{NC} {name} linked to {current or '?'}, replacing...")
                    remove_link_or_junction(link_path)

            # 非链接的文件/目录 → 保护用户数据
            if link_path.exists():
                if force and link_path.is_dir() and (link_path / "SKILL.md").is_file():
                    shutil.rmtree(link_path)
                    print(f"  {YELLOW}[REPLACE]{NC} {name} existing fallback copy")
                elif force and link_path.is_file():
                    link_path.unlink()
                    print(f"  {YELLOW}[REPLACE]{NC} {name} existing file")
                else:
                    print(f"  {YELLOW}[SKIP]{NC} {name} — 目标路径已存在（非链接），跳过")
                    continue

            # 创建链接（或回退复制）
            op = link_or_copy(skill_dir, link_path)
            tag = "LINKED" if op == "linked" else f"COPIED ({op})"
            color = GREEN if op == "linked" else YELLOW
            print(f"  {color}[{tag}]{NC} {name} → {link_path}")

            # pip install
            req = skill_dir / "requirements.txt"
            if do_pip and req.is_file():
                print(f"    {CYAN}pip install -r {name}/requirements.txt...{NC}")
                if pip_install(req):
                    print(f"    {GREEN}[PIP OK]{NC}")
                else:
                    print(f"    {YELLOW}[PIP FAIL]{NC} 请手动执行: pip install -r {req}")


def print_install_summary(result: OperationResult, project_dir: Path) -> None:
    """输出安装操作的结构化 summary。"""
    if _is_json_mode():
        output = {
            "project": str(project_dir),
            "added": result.added,
            "already_installed": result.already,
            "replaced": result.replaced,
            "skipped": [{"skill": s[0], "reason": s[1]} for s in result.skipped],
            "errors": [{"skill": e[0], "error": e[1]} for e in result.errors],
            "project_setup": result.project_setup,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return

    if RICH_AVAILABLE:
        console = get_console()
        console.print()
        console.print(Panel.fit(
            "[bold]Install Summary[/bold]",
            border_style="cyan",
        ))
        console.print(f"Project: [bold]{project_dir}[/bold]")
        console.print()

        if result.added:
            console.print("[bold green]Added:[/bold green]")
            for name in result.added:
                console.print(f"  [green]✓[/green] {name}")
            console.print()

        if result.already:
            console.print("[bold yellow]Already installed:[/bold yellow]")
            for name in result.already:
                console.print(f"  [yellow]-[/yellow] {name}")
            console.print()

        if result.replaced:
            console.print("[bold yellow]Replaced:[/bold yellow]")
            for name in result.replaced:
                console.print(f"  [yellow]↻[/yellow] {name}")
            console.print()

        if result.skipped:
            console.print("[bold yellow]Skipped:[/bold yellow]")
            for name, reason in result.skipped:
                console.print(f"  [yellow]![/yellow] {name}: {reason}")
            console.print()

        if result.errors:
            console.print("[bold red]Errors:[/bold red]")
            for name, error in result.errors:
                console.print(f"  [red]✗[/red] {name}: {error}")
            console.print()

        if result.project_setup:
            console.print("[bold cyan]Project setup:[/bold cyan]")
            for item in result.project_setup:
                console.print(f"  [cyan]✓[/cyan] {item}")
            console.print()
    else:
        print(f"\n{CYAN}{BOLD}Install Summary{NC}")
        print(f"{CYAN}Project:{NC} {BOLD}{project_dir}{NC}\n")

        if result.added:
            print(f"{GREEN}Added:{NC}")
            for name in result.added:
                print(f"  {GREEN}✓{NC} {name}")
            print()

        if result.already:
            print(f"{YELLOW}Already installed:{NC}")
            for name in result.already:
                print(f"  {YELLOW}-{NC} {name}")
            print()

        if result.replaced:
            print(f"{YELLOW}Replaced:{NC}")
            for name in result.replaced:
                print(f"  {YELLOW}↻{NC} {name}")
            print()

        if result.skipped:
            print(f"{YELLOW}Skipped:{NC}")
            for name, reason in result.skipped:
                print(f"  {YELLOW}!{NC} {name}: {reason}")
            print()

        if result.errors:
            print(f"{RED}Errors:{NC}")
            for name, error in result.errors:
                print(f"  {RED}✗{NC} {name}: {error}")
            print()

        if result.project_setup:
            print(f"{CYAN}Project setup:{NC}")
            for item in result.project_setup:
                print(f"  {GREEN}✓{NC} {item}")
            print()

    print_success("Done.")


def print_uninstall_summary(result: OperationResult, project_dir: Path) -> None:
    """输出卸载操作的结构化 summary。"""
    if _is_json_mode():
        output = {
            "project": str(project_dir),
            "removed": result.removed,
            "not_installed": result.not_installed,
            "skipped": [{"skill": s[0], "reason": s[1]} for s in result.skipped],
            "errors": [{"skill": e[0], "error": e[1]} for e in result.errors],
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return

    if RICH_AVAILABLE:
        console = get_console()
        console.print()
        console.print(Panel.fit(
            "[bold]Uninstall Summary[/bold]",
            border_style="cyan",
        ))
        console.print(f"Project: [bold]{project_dir}[/bold]")
        console.print()

        if result.removed:
            console.print("[bold green]Removed:[/bold green]")
            for name in result.removed:
                console.print(f"  [green]✓[/green] {name}")
            console.print()

        if result.not_installed:
            console.print("[bold yellow]Not installed:[/bold yellow]")
            for name in result.not_installed:
                console.print(f"  [yellow]-[/yellow] {name}")
            console.print()

        if result.skipped:
            console.print("[bold yellow]Skipped:[/bold yellow]")
            for name, reason in result.skipped:
                console.print(f"  [yellow]![/yellow] {name}: {reason}")
            console.print()

        if result.errors:
            console.print("[bold red]Errors:[/bold red]")
            for name, error in result.errors:
                console.print(f"  [red]✗[/red] {name}: {error}")
            console.print()
    else:
        print(f"\n{CYAN}{BOLD}Uninstall Summary{NC}")
        print(f"{CYAN}Project:{NC} {BOLD}{project_dir}{NC}\n")

        if result.removed:
            print(f"{GREEN}Removed:{NC}")
            for name in result.removed:
                print(f"  {GREEN}✓{NC} {name}")
            print()

        if result.not_installed:
            print(f"{YELLOW}Not installed:{NC}")
            for name in result.not_installed:
                print(f"  {YELLOW}-{NC} {name}")
            print()

        if result.skipped:
            print(f"{YELLOW}Skipped:{NC}")
            for name, reason in result.skipped:
                print(f"  {YELLOW}!{NC} {name}: {reason}")
            print()

        if result.errors:
            print(f"{RED}Errors:{NC}")
            for name, error in result.errors:
                print(f"  {RED}✗{NC} {name}: {error}")
            print()

    print_success("Done.")


def ensure_gitignore_entries(project_dir: Path, entries: list[str]) -> str | None:
    """将本地 agent 目录加入项目 .gitignore。返回描述字符串或 None。"""
    git = shutil.which("git")
    if git:
        result = subprocess.run(
            [git, "-C", str(project_dir), "rev-parse", "--git-dir"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return None
    else:
        return None

    gitignore = project_dir / ".gitignore"
    existing = set()
    if gitignore.exists():
        existing = {line.strip() for line in gitignore.read_text(encoding="utf-8").splitlines()}
    missing = [entry for entry in entries if entry not in existing]
    if not missing:
        return ".gitignore already contains local agent dirs"
    with gitignore.open("a", encoding="utf-8") as handle:
        if gitignore.exists() and gitignore.stat().st_size > 0:
            handle.write("\n")
        for entry in missing:
            handle.write(f"{entry}\n")
    return f".gitignore added: {', '.join(missing)}"


def ensure_claude_project_link(project_dir: Path, agents_dir: Path) -> str | None:
    """为 Claude Code 建立项目级 .claude/skills 指向 .agents/skills。返回描述字符串或 None。"""
    claude_dir = project_dir / ".claude"
    claude_skills = claude_dir / "skills"
    claude_dir.mkdir(parents=True, exist_ok=True)

    if is_symlink_or_junction(claude_skills) or claude_skills.is_symlink():
        current = read_symlink_target(claude_skills)
        if current in {"../.agents/skills", ".agents/skills"}:
            return ".claude/skills already linked"
        remove_link_or_junction(claude_skills)
    elif claude_skills.exists():
        return ".claude/skills exists; not modified"

    if CAN_SYMLINK:
        os.symlink("../.agents/skills", str(claude_skills), target_is_directory=True)
        return ".claude/skills -> ../.agents/skills"

    op = link_or_copy(agents_dir, claude_skills)
    return f".claude/skills ({op})"


def install_project_skills(skills: list[Path], project_dir: Path, force: bool = False) -> OperationResult:
    """安装技能到当前项目的 .agents/skills。返回结构化结果。"""
    result = OperationResult()
    agents_dir = project_dir / ".agents" / "skills"
    agents_dir.mkdir(parents=True, exist_ok=True)

    # 预扫描：统计已有 skill
    pre_existing: list[str] = []
    pre_blocked: list[tuple[str, str]] = []
    for skill_dir in skills:
        dest = agents_dir / skill_dir.name
        if is_symlink_or_junction(dest) or dest.is_symlink():
            current = read_symlink_target(dest)
            if current and Path(current).resolve() == skill_dir.resolve():
                pre_existing.append(skill_dir.name)
            # wrong link will be replaced — no warning needed
        elif dest.exists():
            pre_blocked.append((skill_dir.name, "exists; not modified" if not force else "will be replaced"))

    if pre_existing and not _is_json_mode():
        print(f"\n{YELLOW}ℹ  {len(pre_existing)} skills already installed in this project (保留现有):{NC}")
        for name in sorted(pre_existing):
            print(f"  {DIM}- {name}{NC}")

    if not _is_json_mode():
        print(f"\n{CYAN}==> Installing to project {agents_dir}{NC}")

    for skill_dir in skills:
        dest = agents_dir / skill_dir.name
        if is_symlink_or_junction(dest) or dest.is_symlink():
            current = read_symlink_target(dest)
            if current and Path(current).resolve() == skill_dir.resolve():
                if not _is_json_mode():
                    print(f"  {YELLOW}[OK]{NC} {skill_dir.name} already installed")
                result.already.append(skill_dir.name)
                continue
            remove_link_or_junction(dest)
        elif dest.exists():
            if force and dest.is_dir() and (dest / "SKILL.md").is_file():
                shutil.rmtree(dest)
                if not _is_json_mode():
                    print(f"  {YELLOW}[REPLACE]{NC} {skill_dir.name} existing fallback copy")
                result.replaced.append(skill_dir.name)
            else:
                reason = "exists; not modified"
                if not _is_json_mode():
                    print(f"  {YELLOW}[SKIP]{NC} {skill_dir.name} {reason}")
                result.skipped.append((skill_dir.name, reason))
                continue

        op = link_or_copy(skill_dir, dest)
        tag = "LINKED" if op == "linked" else op.upper()
        if not _is_json_mode():
            print(f"  {GREEN if op == 'linked' else YELLOW}[{tag}]{NC} {skill_dir.name}")
        result.added.append(skill_dir.name)

    # 项目级设置
    claude_result = ensure_claude_project_link(project_dir, agents_dir)
    if claude_result:
        result.project_setup.append(claude_result)

    gitignore_result = ensure_gitignore_entries(project_dir, [".agents", ".claude"])
    if gitignore_result:
        result.project_setup.append(gitignore_result)

    return result


def uninstall_project_skills(skills: list[Path], project_dir: Path) -> OperationResult:
    """卸载当前项目 .agents/skills 下的技能。返回结构化结果。"""
    result = OperationResult()
    agents_dir = project_dir / ".agents" / "skills"

    if not _is_json_mode():
        print(f"\n{CYAN}==> Uninstalling from project {agents_dir}{NC}")

    if not agents_dir.is_dir():
        msg = "project skills directory does not exist"
        if not _is_json_mode():
            print(f"  {YELLOW}[MISSING]{NC} {msg}")
        result.errors.append(("", msg))
        return result

    for skill_dir in skills:
        dest = agents_dir / skill_dir.name
        if is_symlink_or_junction(dest) or dest.is_symlink():
            remove_link_or_junction(dest)
            if not _is_json_mode():
                print(f"  {GREEN}[REMOVED]{NC} {skill_dir.name}")
            result.removed.append(skill_dir.name)
        elif dest.is_dir() and (dest / "SKILL.md").is_file():
            shutil.rmtree(dest)
            if not _is_json_mode():
                print(f"  {GREEN}[REMOVED]{NC} {skill_dir.name} (was a fallback copy)")
            result.removed.append(skill_dir.name)
        elif dest.exists():
            reason = "exists but is not a managed skill entry"
            if not _is_json_mode():
                print(f"  {YELLOW}[SKIP]{NC} {skill_dir.name} {reason}")
            result.skipped.append((skill_dir.name, reason))
        else:
            if not _is_json_mode():
                print(f"  {GREEN}[NONE]{NC} {skill_dir.name} 未安装")
            result.not_installed.append(skill_dir.name)

    return result


def status_skills(
    targets: list[Path],
    json_output: bool = False,
    no_color: bool = False,
    project_dir: Path | None = None,
) -> None:
    """显示各目标平台下的技能安装状态。

    支持项目状态（--project）和全局状态。
    """
    available = {d.name for d in select_skills(None)}

    if project_dir is not None:
        _status_project(project_dir, available, json_output, no_color)
        return

    # 全局状态
    if json_output:
        _status_global_json(targets, available)
        return

    for target_dir in targets:
        _status_global_rich(target_dir, available, no_color)


def _status_project(
    project_dir: Path,
    available: set[str],
    json_output: bool,
    no_color: bool,
) -> None:
    """显示项目级 skill 状态。"""
    agents_dir = project_dir / ".agents" / "skills"
    rows: list[dict[str, str]] = []

    if agents_dir.is_dir():
        for path in sorted(agents_dir.iterdir()):
            if path.name in available:
                status = "linked" if (is_symlink_or_junction(path) or path.is_symlink()) else "copied"
                target = ""
                if is_symlink_or_junction(path) or path.is_symlink():
                    target = read_symlink_target(path) or ""
                rows.append({"name": path.name, "status": status, "target": target})

    # 添加未安装的 skill
    installed_names = {r["name"] for r in rows}
    for name in sorted(available):
        if name not in installed_names:
            rows.append({"name": name, "status": "not installed", "target": "-"})

    if json_output:
        print(json.dumps({
            "project": str(project_dir),
            "skills": rows,
        }, ensure_ascii=False, indent=2))
        return

    table_rows = [[r["name"], r["status"], r["target"]] for r in rows]
    print_table(
        f"Project Skill Status\nProject: {project_dir}",
        ["Skill", "Status", "Target"],
        table_rows,
        no_color=no_color,
    )


def _status_global_json(targets: list[Path], available: set[str]) -> None:
    """JSON 格式输出全局状态。"""
    output: dict[str, Any] = {"targets": {}}
    for target_dir in targets:
        target_name = target_dir.name
        skills_list: list[dict[str, str]] = []
        if target_dir.is_dir():
            for path in sorted(target_dir.iterdir()):
                if path.name in available:
                    kind = "link" if is_symlink_or_junction(path) or path.is_symlink() else "copy"
                    skills_list.append({"name": path.name, "kind": kind})
        output["targets"][target_name] = {
            "path": str(target_dir),
            "skills": skills_list,
        }
    print(json.dumps(output, ensure_ascii=False, indent=2))


def _status_global_rich(target_dir: Path, available: set[str], no_color: bool) -> None:
    """Rich 表格输出单个全局目标的状态。"""
    if not target_dir.is_dir():
        if RICH_AVAILABLE:
            get_console(no_color).print(f"\n[yellow][MISSING][/yellow] {target_dir} does not exist")
        else:
            print(f"\n{YELLOW}[MISSING]{NC} {target_dir} does not exist")
        return

    installed = []
    for path in sorted(target_dir.iterdir()):
        if path.name in available:
            kind = "link" if is_symlink_or_junction(path) or path.is_symlink() else "copy"
            installed.append((path.name, kind))

    if not installed:
        if RICH_AVAILABLE:
            get_console(no_color).print(f"\n[yellow][EMPTY][/yellow] {target_dir}: no known skills installed")
        else:
            print(f"\n{YELLOW}[EMPTY]{NC} {target_dir}: no known skills installed")
        return

    rows = [[name, kind] for name, kind in installed]
    print_table(
        f"Global Skill Status: {target_dir}",
        ["Skill", "Kind"],
        rows,
        no_color=no_color,
    )


def git_pull_repo() -> bool:
    """更新当前仓库，成功或无 Git 仓库时返回是否可继续安装。"""
    git = shutil.which("git")
    if not git:
        print_warning("git not found in PATH; skip repository update.")
        return True
    result = subprocess.run([git, "-C", str(REPO_DIR), "pull", "--ff-only"])
    if result.returncode != 0:
        print_error("git pull --ff-only failed; fix the repository state and retry.")
        return False
    return True


def run_checked(command: list[str], cwd: Path | None = None) -> bool:
    """运行命令并返回是否成功。"""
    result = subprocess.run(command, cwd=str(cwd) if cwd else None)
    return result.returncode == 0


def load_skills_manifest() -> dict:
    """读取 skills-manifest.json。"""
    if not MANIFEST.exists():
        print_warning("skills-manifest.json not found; skip upstream update.")
        return {"skills": {}}
    return json.loads(MANIFEST.read_text(encoding="utf-8-sig"))


def save_skills_manifest(manifest: dict) -> None:
    """写回 skills-manifest.json。"""
    manifest["updated"] = date.today().isoformat()
    MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def update_manifest_schema() -> bool:
    """根据 manifest 中实际使用的值自动更新 schema enum，并验证 manifest 合法性。"""
    manifest = load_skills_manifest()
    if not manifest.get("skills"):
        return True

    # 收集实际使用的 type / update 值
    used_types: set[str] = set()
    used_updates: set[str] = set()
    for meta in manifest["skills"].values():
        t = meta.get("type")
        u = meta.get("update")
        if isinstance(t, str) and t:
            used_types.add(t)
        if isinstance(u, str) and u:
            used_updates.add(u)

    # 读取或初始化 schema
    if SCHEMA.exists():
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    else:
        schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": "localagentskills manifest",
            "type": "object",
            "required": ["version", "updated", "skills"],
            "additionalProperties": False,
            "properties": {
                "version": {"type": "integer", "minimum": 1},
                "updated": {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}$"},
                "skills": {
                    "type": "object",
                    "additionalProperties": {
                        "type": "object",
                        "required": ["type", "source", "update", "notes"],
                        "additionalProperties": False,
                        "properties": {
                            "type": {"type": "string"},
                            "source": {"type": ["string", "null"], "minLength": 1},
                            "update": {"type": "string"},
                            "notes": {"type": "string", "minLength": 1},
                        },
                    },
                },
            },
        }

    # 更新 type enum
    props = schema["properties"]["skills"]["additionalProperties"]["properties"]
    if "enum" not in props["type"]:
        props["type"]["enum"] = []
    existing_types = set(props["type"]["enum"])
    new_types = used_types - existing_types
    if new_types:
        props["type"]["enum"] = sorted(existing_types | used_types)
        print(f"  {CYAN}[SCHEMA]{NC} type enum +{new_types}")

    # 更新 update enum
    if "enum" not in props["update"]:
        props["update"]["enum"] = []
    existing_updates = set(props["update"]["enum"])
    new_updates = used_updates - existing_updates
    if new_updates:
        props["update"]["enum"] = sorted(existing_updates | used_updates)
        print(f"  {CYAN}[SCHEMA]{NC} update enum +{new_updates}")

    # 验证 manifest 结构合法性
    manifest_skills = manifest.get("skills", {})
    errors: list[str] = []
    for name, meta in manifest_skills.items():
        if not isinstance(meta, dict):
            errors.append(f"{name}: entry is not a dict")
            continue
        t = meta.get("type")
        u = meta.get("update")
        if t not in props["type"].get("enum", []):
            errors.append(f"{name}: unknown type '{t}'")
        if u not in props["update"].get("enum", []):
            errors.append(f"{name}: unknown update '{u}'")
        if not isinstance(meta.get("notes"), str) or not meta["notes"]:
            errors.append(f"{name}: missing or empty 'notes'")

    if errors:
        for err in errors:
            print_error(f"Schema validation: {err}")
        return False

    SCHEMA.write_text(
        json.dumps(schema, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return True


def ensure_manifest_entries() -> bool:
    """以 skills/ 目录为准，补充新增 skill，删除已不存在的 skill 条目。"""
    manifest = load_skills_manifest()
    entries = manifest.setdefault("skills", {})
    active_names = {d.name for d in select_skills(None)}
    changed = False

    # 删除 manifest 中指向不存在 skill 的条目
    stale = [name for name in entries if name not in active_names]
    for name in stale:
        del entries[name]
        print(f"{YELLOW}[MANIFEST]{NC} removed stale entry: {name}")
        changed = True

    # 为本地新增 skill 自动补充条目
    for name in sorted(active_names):
        if name in entries:
            continue
        entries[name] = {
            "type": "custom",
            "source": None,
            "update": "local",
            "notes": "localagentskills update 自动登记；请按需补充来源和同步策略。",
        }
        print(f"{GREEN}[MANIFEST]{NC} added local skill: {name}")
        changed = True

    if changed:
        save_skills_manifest(manifest)
    return True


def normalize_skill_name(name: str) -> str:
    """归一化 skill 名，用于匹配上游目录和 frontmatter。"""
    return "".join(ch for ch in name.lower() if ch.isalnum())


def read_skill_name(skill_md: Path) -> str:
    """读取 SKILL.md frontmatter name。"""
    try:
        text = skill_md.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    if not text.startswith("---"):
        return ""
    parts = text.split("---", 2)
    if len(parts) < 3:
        return ""
    for line in parts[1].splitlines():
        if line.startswith("name:"):
            return line.split(":", 1)[1].strip().strip("\"'")
    return ""


def find_upstream_skill_dir(repo_dir: Path, skill_name: str) -> Path | None:
    """在上游仓库中定位某个 skill 的目录。"""
    candidates = [
        repo_dir / "skills" / skill_name,
        repo_dir / skill_name,
        repo_dir / skill_name.replace("-", "_"),
        repo_dir,
    ]
    for candidate in candidates:
        if (candidate / "SKILL.md").is_file():
            return candidate

    wanted = normalize_skill_name(skill_name)
    for skill_md in repo_dir.rglob("SKILL.md"):
        parent = skill_md.parent
        if normalize_skill_name(parent.name) == wanted:
            return parent
        frontmatter_name = read_skill_name(skill_md)
        if normalize_skill_name(frontmatter_name) == wanted:
            return parent
    return None


def replace_skill_from_upstream(skill_name: str, upstream_dir: Path) -> None:
    """用上游 skill 目录替换本地 skill。"""
    dest = SKILLS_DIR / skill_name
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(
        upstream_dir,
        dest,
        ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc", ".DS_Store"),
    )


def sync_github_skills(skill_filter: list[str] | None = None) -> bool:
    """根据 manifest 直接从 GitHub 最新内容同步到本地 skills/。"""
    git = shutil.which("git")
    if not git:
        print_warning("git not found in PATH; skip online skill sync.")
        return True

    manifest = load_skills_manifest().get("skills", {})
    wanted = set(skill_filter or [])
    by_source: dict[str, list[str]] = {}
    for skill_name, meta in sorted(manifest.items()):
        if wanted and skill_name not in wanted:
            continue
        source = meta.get("source")
        if isinstance(source, str) and "github.com" in source:
            by_source.setdefault(source, []).append(skill_name)

    ok = True
    with tempfile.TemporaryDirectory(prefix="localagentskills-update-") as temp:
        temp_dir = Path(temp)
        for index, (source, skill_names) in enumerate(sorted(by_source.items()), start=1):
            repo_dir = temp_dir / f"repo-{index}"
            print(f"{CYAN}==> Clone latest upstream {source}{NC}")
            if not run_checked([git, "clone", "--depth", "1", source, str(repo_dir)]):
                ok = False
                continue
            for skill_name in skill_names:
                upstream_skill = find_upstream_skill_dir(repo_dir, skill_name)
                if upstream_skill is None:
                    print_warning(f"{skill_name}: cannot locate SKILL.md in upstream")
                    ok = False
                    continue
                replace_skill_from_upstream(skill_name, upstream_skill)
                print(f"  {GREEN}[SYNCED]{NC} {skill_name} <- {upstream_skill.relative_to(repo_dir)}")
    return ok


def regenerate_readme_and_audit() -> bool:
    """重新生成 README 表格并运行审计。"""
    generator = REPO_DIR / "scripts" / "generate-readme.py"
    auditor = REPO_DIR / "scripts" / "audit-skills.py"
    ok = True
    if generator.exists():
        print(f"{CYAN}==> Regenerate README skill table{NC}")
        ok &= run_checked([sys.executable, str(generator)], REPO_DIR)
    else:
        print_warning("scripts/generate-readme.py not found.")
    if auditor.exists():
        print(f"{CYAN}==> Audit skills metadata{NC}")
        ok &= run_checked([sys.executable, str(auditor)], REPO_DIR)
    else:
        print_warning("scripts/audit-skills.py not found.")
    return ok


def update_repository_and_resources(args: argparse.Namespace) -> bool:
    """更新仓库、在线 skill 内容、manifest、schema 和 README 文档。"""
    ok = True
    if not args.no_pull:
        ok &= git_pull_repo()
        if not ok:
            return False
    ok &= ensure_manifest_entries()
    if not args.no_sync:
        ok &= sync_github_skills(args.skills or None)
        ok &= ensure_manifest_entries()
    ok &= update_manifest_schema()
    if not args.no_readme:
        ok &= regenerate_readme_and_audit()
    return ok


# ── 卸载交互选择 ──────────────────────────────────────────────

def choose_uninstall_skills(project_dir: Path) -> list[Path]:
    """交互式选择要卸载的技能（仅列出已安装的）。"""
    agents_dir = project_dir / ".agents" / "skills"
    if not agents_dir.is_dir():
        print_warning("No project skills directory found.")
        return []

    installed: list[Path] = []
    for path in sorted(agents_dir.iterdir()):
        if (path.is_symlink() or is_symlink_or_junction(path) or
                (path.is_dir() and (path / "SKILL.md").is_file())):
            installed.append(path)

    if not installed:
        print_warning("No installed skills found.")
        return []

    if not sys.stdin.isatty():
        # 非 TTY: 返回全部已安装 skill
        names = [p.name for p in installed]
        # 映射回 SKILLS_DIR
        result = []
        for name in names:
            skill_path = SKILLS_DIR / name
            if skill_path.is_dir() and (skill_path / "SKILL.md").is_file():
                result.append(skill_path)
        return result

    if INQUIRER_AVAILABLE:
        try:
            choices = [
                Choice(value=p.name, name=f"{p.name:<36} (installed)", enabled=False)
                for p in installed
            ]
            selected_names = inquirer.checkbox(
                message="Select skills to uninstall:",
                choices=choices,
                instruction="Space: toggle · Ctrl-A: all · Enter: confirm",
            ).execute()
        except KeyboardInterrupt:
            print()
            print_warning("Cancelled.")
            return []

        if not selected_names:
            return []

        result = []
        for name in selected_names:
            skill_path = SKILLS_DIR / name
            if skill_path.is_dir() and (skill_path / "SKILL.md").is_file():
                result.append(skill_path)
        return result

    # Fallback: 使用编号选择
    print(f"\n{CYAN}Installed skills in project:{NC}")
    for index, p in enumerate(installed, start=1):
        print(f"  {YELLOW}{index:2d}){NC} {BOLD}{p.name}{NC}")

    print(f"\n{CYAN}输入编号卸载（如 1 3 5 或 1-4），输入 a 全选，直接回车退出：{NC}", end="")
    selection = input().strip()
    if not selection:
        return []
    if selection.lower() == "a":
        indexes = list(range(len(installed)))
    else:
        indexes = parse_selection(selection, len(installed))

    result = []
    for i in indexes:
        name = installed[i].name
        skill_path = SKILLS_DIR / name
        if skill_path.is_dir() and (skill_path / "SKILL.md").is_file():
            result.append(skill_path)
    return result


# ── 全局卸载 ──────────────────────────────────────────────────

def _uninstall_global_skills(skills: list[Path], targets: list[Path]) -> None:
    """卸载全局安装目录中的 skill。"""
    for target_dir in targets:
        if not target_dir.is_dir():
            continue
        for skill_dir in skills:
            name = skill_dir.name
            link_path = target_dir / name
            if is_symlink_or_junction(link_path) or link_path.is_symlink():
                remove_link_or_junction(link_path)
                print(f"  {GREEN}[REMOVED]{NC} {name} from {target_dir}")
            elif link_path.is_dir() and (link_path / "SKILL.md").is_file():
                shutil.rmtree(link_path)
                print(f"  {GREEN}[REMOVED]{NC} {name} from {target_dir} (was a copy)")
            elif link_path.exists():
                print(f"  {YELLOW}[SKIP]{NC} {name} — 目标存在但不是 managed entry")
            else:
                print(f"  {DIM}[NONE]{NC} {name} — 未安装在 {target_dir}")


# ── 入口 ──────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="localagentskills",
        description="跨平台管理 localagentskills 到 Claude Code / Codex",
    )
    parser.add_argument("--no-color", action="store_true", help="禁用彩色输出")

    subparsers = parser.add_subparsers(dest="command")

    # install
    install_parser = subparsers.add_parser("install", help="安装技能到当前项目")
    install_parser.add_argument("skills", nargs="*", help="技能名；省略则进入交互选择")
    install_parser.add_argument("--project", default=".", help="目标项目目录 (default: 当前目录)")
    install_parser.add_argument("--all", action="store_true", help="安装全部技能；配合 --global 时安装全部全局技能")
    install_parser.add_argument("--global", dest="global_install", action="store_true",
                                help="改为安装到全局 Claude/Codex 技能目录")
    install_parser.add_argument("--target", default="both", choices=["claude", "codex", "both"],
                                help="仅配合 --global 使用的目标平台 (default: both)")
    install_parser.add_argument("--pip", dest="do_pip", action="store_true",
                                help="仅配合 --global 使用，同时安装 requirements.txt")
    install_parser.add_argument("--force", action="store_true",
                                help="替换已存在的回退副本")
    install_parser.add_argument("--json", action="store_true",
                                help="输出 JSON 格式结果")

    # update
    update_parser = subparsers.add_parser("update", help="更新仓库、在线 skill 内容、manifest 和 README")
    update_parser.add_argument("skills", nargs="*", help="只同步指定 skill；省略则同步全部 GitHub 来源")
    update_parser.add_argument("--no-pull", action="store_true",
                               help="跳过当前仓库 git pull")
    update_parser.add_argument("--no-sync", "--no-upstreams", action="store_true",
                               help="跳过在线 GitHub skill 同步")
    update_parser.add_argument("--no-readme", action="store_true",
                               help="跳过 README 生成和审计")

    # uninstall
    uninstall_parser = subparsers.add_parser("uninstall", help="卸载当前项目中的技能")
    uninstall_parser.add_argument("skills", nargs="*", help="技能名；省略则进入交互选择")
    uninstall_parser.add_argument("--project", default=".", help="目标项目目录 (default: 当前目录)")
    uninstall_parser.add_argument("--all", action="store_true", help="卸载全部已安装技能；配合 --global 时卸载全部全局技能")
    uninstall_parser.add_argument("--global", dest="global_uninstall", action="store_true",
                                  help="改为卸载全局 Claude/Codex 技能目录中的技能")
    uninstall_parser.add_argument("--target", default="both", choices=["claude", "codex", "both"],
                                  help="仅配合 --global 使用的目标平台 (default: both)")
    uninstall_parser.add_argument("--json", action="store_true",
                                  help="输出 JSON 格式结果")

    # status
    status_parser = subparsers.add_parser("status", help="查看当前项目安装状态")
    status_parser.add_argument("--target", default="both", choices=["claude", "codex", "both"],
                               help="仅配合 --global 使用的目标平台 (default: both)")
    status_parser.add_argument("--project", default=".", help="目标项目目录 (default: 当前目录)")
    status_parser.add_argument("--json", action="store_true", help="输出 JSON 格式")
    status_parser.add_argument("--global", dest="global_status", action="store_true",
                               help="改为查看全局安装状态")

    # list
    list_parser = subparsers.add_parser("list", help="列出仓库中的可用技能")
    list_parser.add_argument("--json", action="store_true", help="输出 JSON 格式")

    args = parser.parse_args()

    # 设置 JSON 模式环境变量
    json_output = getattr(args, "json", False)
    if json_output:
        os.environ["LOCALAGENTSKILLS_JSON"] = "1"

    no_color = getattr(args, "no_color", False)

    # 无子命令时显示帮助
    if args.command is None:
        parser.print_help()
        return

    if args.command == "list":
        list_skills(json_output=json_output, no_color=no_color)
        return

    if args.command == "status":
        if getattr(args, "global_status", False):
            targets = target_dirs(getattr(args, "target", "both"))
            status_skills(
                targets,
                json_output=json_output,
                no_color=no_color,
                project_dir=None,
            )
        else:
            project_dir = Path(getattr(args, "project", ".")).expanduser().resolve()
            status_skills(
                [],
                json_output=json_output,
                no_color=no_color,
                project_dir=project_dir,
            )
        return

    if args.command == "update":
        if update_repository_and_resources(args):
            print(f"\n{GREEN}Done.{NC}")
        else:
            print(f"\n{RED}Update finished with errors.{NC}")
            sys.exit(1)
        return

    if args.command == "install":
        if getattr(args, "global_install", False):
            # 全局安装
            targets = target_dirs(getattr(args, "target", "both"))
            if args.all:
                skills = select_skills(None)
            elif args.skills:
                skills = select_skills(args.skills)
            else:
                skills = choose_global_install_skills(targets)
            if not skills:
                if json_output:
                    print(json.dumps({"error": "No skills selected", "skills": []}))
                else:
                    print_warning("未选择任何 skill，退出。")
                return
            if not CAN_SYMLINK:
                print_warning("符号链接不可用（Windows 需管理员权限或开发者模式），将回退到复制。")
                print_warning("       回退复制不会自动同步上游更新，建议开启开发者模式后重试。")
            install_skills(skills, targets, getattr(args, "do_pip", False), getattr(args, "force", False))
            print_success("Done.")
            return
        else:
            # 项目级安装
            project_dir = Path(args.project).expanduser().resolve()
            if args.all:
                skills = select_skills(None)
            elif args.skills:
                skills = select_skills(args.skills)
            else:
                skills = choose_project_skills(project_dir)
            if not skills:
                if json_output:
                    print(json.dumps({"error": "No skills selected", "skills": []}))
                else:
                    print_warning("未选择任何 skill，退出。")
                return
            result = install_project_skills(skills, project_dir, args.force)
            print_install_summary(result, project_dir)
            return

    if args.command == "uninstall":
        if getattr(args, "global_uninstall", False):
            # 全局卸载
            targets = target_dirs(getattr(args, "target", "both"))
            if getattr(args, "all", False):
                skills = global_installed_skill_paths(targets)
            elif args.skills:
                skills = select_skills(args.skills)
            else:
                skills = choose_global_uninstall_skills(targets)
            if not skills:
                if json_output:
                    print(json.dumps({"error": "No skills selected", "skills": []}))
                else:
                    print_warning("未选择任何 skill，退出。")
                return
            _uninstall_global_skills(skills, targets)
            print_success("Done.")
            return
        else:
            # 项目级卸载
            project_dir = Path(getattr(args, "project", ".")).expanduser().resolve()
            if getattr(args, "all", False):
                skills = select_skills(None)
            elif args.skills:
                skills = select_skills(args.skills)
            else:
                skills = choose_uninstall_skills(project_dir)
            if not skills:
                if json_output:
                    print(json.dumps({"error": "No skills selected", "skills": []}))
                else:
                    print_warning("未选择任何 skill，退出。")
                return
            result = uninstall_project_skills(skills, project_dir)
            print_uninstall_summary(result, project_dir)
            return


if __name__ == "__main__":
    main()
