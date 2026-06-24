# Repository Guidelines

## Project Structure & Module Organization

This repository stores reusable Agent/Codex skills. The root contains installer entry points:

- `install.py`: cross-platform installer for Claude Code and Codex skill directories.
- `skill-install.sh`: interactive shell installer for selecting skills into a target project.
- `skills/<skill-name>/SKILL.md`: required skill definition file.
- `skills/<skill-name>/scripts/`: optional executable helpers for that skill.
- `skills/<skill-name>/references/`: optional supporting documentation.
- `skills/<skill-name>/agents/openai.yaml`: optional Codex-specific agent configuration.
- `skills/<skill-name>/tests/`: optional test files for scriptable behavior.

Keep each skill self-contained. Shared assumptions should be documented in the relevant `SKILL.md` or `references/` file instead of hidden in installer logic.

## Build, Test, and Development Commands

- `python install.py --list`: list available skills detected under `skills/`.
- `python install.py`: install all skills to the supported local agent platforms.
- `python install.py --skill <skill-name>`: install one skill for local verification.
- `python install.py --target claude`: install only to Claude Code.
- `python install.py --pip`: install declared Python dependencies where supported.
- `bash skill-install.sh [target-project]`: interactively select skills for a project.

There is no central build step. Validate with the relevant installer command and any skill-specific test script, such as `bash skills/ai-spend-audit/tests/run_all.sh`.

## Coding Style & Naming Conventions

Use clear, portable Python and Bash. Follow the existing style: 4-space indentation for Python, `set -euo pipefail` for Bash scripts, and descriptive helper names. Skill directories use lowercase kebab-case, for example `web-novel-downloader`. Required skill files must be named exactly `SKILL.md`.

Prefer relative paths inside skills so the repository can be cloned or installed anywhere. Avoid broad refactors when updating a single skill.

## Testing Guidelines

Add tests near the skill they verify, usually under `skills/<skill-name>/tests/`. Name Python tests `test_*.py` and shell runners `run_all.sh`. For installer changes, verify at least `python install.py --list` and one targeted install command.

## Commit & Pull Request Guidelines

Recent history uses Conventional Commit-style prefixes such as `feat:` and `fix:`. Keep commit subjects imperative and focused, for example `fix: preserve relative skill symlinks`.

Pull requests should include a short description, affected skills or scripts, verification commands run, and any platform-specific notes. Add screenshots only for visual assets or user-facing installer output.

## Security & Configuration Tips

Do not commit credentials, local agent state, generated private reports, or machine-specific paths. When adding scripts that install dependencies or touch user directories, document the target paths and provide a dry-run or listing command when practical.
