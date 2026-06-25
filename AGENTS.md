# Repository Guidelines

## Project Structure & Module Organization

This repository stores reusable Agent/Codex skills. The root contains installer entry points:

- `install.py`: cross-platform CLI for managing skills in Claude Code and Codex.
- `skills/<skill-name>/SKILL.md`: required skill definition file.
- `skills/<skill-name>/scripts/`: optional executable helpers for that skill.
- `skills/<skill-name>/references/`: optional supporting documentation.
- `skills/<skill-name>/agents/openai.yaml`: optional Codex-specific agent configuration.
- `skills/<skill-name>/tests/`: optional test files for scriptable behavior.

Keep each skill self-contained. Shared assumptions should be documented in the relevant `SKILL.md` or `references/` file instead of hidden in installer logic.

## Build, Test, and Development Commands

- `python3 install.py list`: list available skills detected under `skills/`.
- `python3 install.py install <skill-name>`: install one skill to the current project for local verification.
- `python3 install.py install --all`: install all skills to the current project.
- `python3 install.py install --global`: install all skills globally to Claude Code and Codex.
- `python3 install.py install --global --target claude`: install globally only to Claude Code.
- `python3 install.py uninstall <skill-name>`: uninstall a skill from the current project.
- `python3 install.py status`: show global installation status.
- `python3 install.py status --project .`: show current project installation status.

There is no central build step. Validate with the relevant installer command and any skill-specific test script, such as `bash skills/ai-spend-audit/tests/run_all.sh`.

## Coding Style & Naming Conventions

Use clear, portable Python and Bash. Follow the existing style: 4-space indentation for Python, `set -euo pipefail` for Bash scripts, and descriptive helper names. Skill directories use lowercase kebab-case, for example `web-novel-downloader`. Required skill files must be named exactly `SKILL.md`.

Prefer relative paths inside skills so the repository can be cloned or installed anywhere. Avoid broad refactors when updating a single skill.

## Testing Guidelines

Add tests near the skill they verify, usually under `skills/<skill-name>/tests/`. Name Python tests `test_*.py` and shell runners `run_all.sh`. For installer changes, verify at least `python3 install.py list` and one targeted install command.

## Commit & Pull Request Guidelines

Recent history uses Conventional Commit-style prefixes such as `feat:` and `fix:`. Keep commit subjects imperative and focused, for example `fix: preserve relative skill symlinks`.

Pull requests should include a short description, affected skills or scripts, verification commands run, and any platform-specific notes. Add screenshots only for visual assets or user-facing installer output.

## Security & Configuration Tips

Do not commit credentials, local agent state, generated private reports, or machine-specific paths. When adding scripts that install dependencies or touch user directories, document the target paths and provide a dry-run or listing command when practical.
