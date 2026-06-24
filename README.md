# Agent Skills Hub

统一管理本地 Agent Skills 的仓库。当前仓库集中保存 Claude Code / Codex 可复用的 skills，并提供两种安装方式：

- **推荐**：按项目安装到 `<project>/.agents/skills`，再让 `<project>/.claude/skills` 指向同一份目录。
- **备用**：全局安装到 `~/.claude/skills` / `~/.codex/skills`。

> 仓库名目前仍是 `PersonalSkills`。如果后续要更准确地表达“统一 skills 仓库”，可以考虑改名为 `AgentSkillsHub`、`LocalAgentSkills` 或 `PersonalAgentSkills`。

## 这个仓库解决什么问题

- 集中保存所有本地 skill，避免分散在不同项目或用户目录里。
- 支持按项目选择性启用 skill，减少每个项目的上下文污染。
- 同一份 skill 可以被 Claude Code、Codex 或项目级 agent 配置复用。
- 为 GitHub / 网上来源 / 自制 / 内部定制 skill 记录来源，方便未来同步更新。
- 用软链接安装，仓库更新后目标项目可自动使用最新本地版本。

## 目录结构

```text
skills/
  <skill-name>/
    SKILL.md          # skill 定义，必须存在
    scripts/           # 可执行脚本，可选
    references/        # 参考文档，可选
    agents/            # Codex 专用配置，可选

scripts/
  generate-readme.py   # 根据 SKILL.md 和 skills-manifest.json 生成 README skill 表格
  audit-skills.py      # 检查 manifest 覆盖、frontmatter 和 README 生成状态

skills-manifest.json        # skill 来源、同步策略和维护备注
skills-manifest.schema.json # manifest 字段约束说明
skill-install.sh            # 推荐：安装到指定项目
install.py                  # 备用：全局安装到 Claude Code / Codex 用户目录
```

## 推荐安装方式：安装到某个项目

使用 `skill-install.sh` 把本仓库中的 skill 选择性链接到目标项目：

```bash
./skill-install.sh /path/to/project
```

如果不传目标目录，脚本会询问，默认使用当前目录：

```bash
./skill-install.sh
```

安装后目标项目结构大致为：

```text
<project>/
  .agents/skills/<skill-name>  ->  本仓库 skills/<skill-name>
  .claude/skills               ->  ../.agents/skills
```

脚本会：

- 使用 `fzf` 多选 skill；没有 `fzf` 时回退到编号选择。
- 已安装的 skill 会默认排在前面并预选。
- 给 Git 项目自动把 `.agents` 和 `.claude` 加入 `.gitignore`。
- 默认使用软链接，因此更新本仓库后，目标项目会使用最新本地版本。

## 备用安装方式：全局安装到用户目录

`install.py` 是全局安装脚本，会把 skill 安装到：

```text
~/.claude/skills
~/.codex/skills
```

常用命令：

```bash
# 查看可用 skill
python3 install.py --list

# 安装全部 skill 到 Claude Code + Codex
python3 install.py

# 只安装到 Claude Code
python3 install.py --target claude

# 只安装到 Codex
python3 install.py --target codex

# 只安装指定 skill
python3 install.py --skill web-novel-downloader

# 同时安装 requirements.txt 依赖
python3 install.py --pip

# 卸载由脚本安装的 skill
python3 install.py --uninstall
```

如果主要使用项目级 `.agents/skills` 工作流，可以忽略 `install.py`。暂时保留它是为了兼容全局 skill 使用方式。

## Skill 列表

<!-- SKILLS_TABLE_START -->
| Skill | 描述 | 来源 | 更新策略 |
|---|---|---|---|
| [agent-reach](skills/agent-reach/) | MUST USE when user wants to 调研/research/搜索/search/查/找/look up anything on the internet — e.g. 全… | [GitHub](https://github.com/Panniantong/Agent-Reach) | 手动 diff 同步 |
| [ai-spend-audit](skills/ai-spend-audit/) | 分析最近 N 天(默认 7 天,支持任意天)的全部 AI 耗量与花费,横跨 Claude Code、Codex、XDT Maker、OpenClaw 等本地 session,可通过 prov… | 自制 | 本地维护 |
| [caveman](skills/caveman/) | Ultra-compressed communication mode. Cuts token usage ~75% by dropping filler, articles, and pl… | 自制 | 本地维护 |
| [codex-review](skills/codex-review/) | Codex code review closeout: local dirty changes, PR branch vs main, parallel tests. | 自制 | 本地维护 |
| [diagnose](skills/diagnose/) | Disciplined diagnosis loop for hard bugs and performance regressions. Reproduce → minimise → hy… | 自制 | 本地维护 |
| [find-skills](skills/find-skills/) | Helps users discover and install agent skills when they ask questions like "how do I do X", "fi… | [网上](https://skills.sh/) | 手动 diff 同步 |
| [git-cherry-pick](skills/git-cherry-pick/) | Ports a batch of commits from a source git branch onto the current branch using cherry-pick, in… | 自制 | 本地维护 |
| [grill-me](skills/grill-me/) | Interview the user relentlessly about a plan or design until reaching shared understanding, res… | [GitHub](https://github.com/mattpocock/skills) | 手动 diff 同步 |
| [grill-with-docs](skills/grill-with-docs/) | Grilling session that challenges your plan against the existing domain model, sharpens terminol… | [GitHub](https://github.com/mattpocock/skills) | 手动 diff 同步 |
| [handoff](skills/handoff/) | Compact the current conversation into a handoff document for another agent to pick up. | [GitHub](https://github.com/mattpocock/skills) | 手动 diff 同步 |
| [hatch-pet](skills/hatch-pet/) | Create, repair, validate, preview, and package Codex-compatible animated pets and pet spriteshe… | 第三方 | 手动 diff 同步 |
| [improve-codebase-architecture](skills/improve-codebase-architecture/) | Find deepening opportunities in a codebase, informed by the domain language in CONTEXT.md and t… | [GitHub](https://github.com/mattpocock/skills) | 手动 diff 同步 |
| [jira-fullstack-orchestrator](skills/jira-fullstack-orchestrator/) | Use this skill when a Jira-driven feature needs coordinated planning and execution across multi… | 内部 | 本地维护 |
| [jira-proto-to-main](skills/jira-proto-to-main/) | Given a Jira issue such as TTDBL-42165, locate the corresponding proto commits in /Users/songdc… | 内部 | 本地维护 |
| [jira-submit-to-git](skills/jira-submit-to-git/) | Submit Jira-related local changes from one of the configured XD repositories directly to the re… | 内部 | 本地维护 |
| [jira-unity-to-main](skills/jira-unity-to-main/) | Read a Jira issue, extract its summary, review and validate existing local Unity changes, then… | 内部 | 本地维护 |
| [jira-unity-to-tw](skills/jira-unity-to-tw/) | Move Jira-related Unity commits onto the TW branch in this project, with commit lookup, depende… | 内部 | 本地维护 |
| [last30days](skills/last30days/) | Research what people actually say about any topic in the last 30 days. Pulls posts and engageme… | [GitHub](https://github.com/mvanhorn/last30days-skill) | 手动 diff 同步 |
| [pdf](skills/pdf/) | Use when tasks involve reading, creating, or reviewing PDF files where rendering and layout mat… | 第三方 | 手动 diff 同步 |
| [prototype](skills/prototype/) | Build a throwaway prototype to flesh out a design before committing to it. Routes between two b… | [GitHub](https://github.com/mattpocock/skills) | 手动 diff 同步 |
| [setup-matt-pocock-skills](skills/setup-matt-pocock-skills/) | Sets up an `## Agent skills` block in AGENTS.md/CLAUDE.md and `docs/agents/` so the engineering… | [GitHub](https://github.com/mattpocock/skills) | 手动 diff 同步 |
| [tdd](skills/tdd/) | Test-driven development with red-green-refactor loop. Use when user wants to build features or… | [GitHub](https://github.com/mattpocock/skills) | 手动 diff 同步 |
| [tech-doc-style-chinese](skills/tech-doc-style-chinese/) | 在撰写、改写或审阅中文技术文档、文档首页、产品文案、界面文案、Markdown 文档或接口说明时使用。采用克制、准确、可扫读的中文技术写作风格：避免第二人称和宣传腔，统一使用直角引号，在可见… | [GitHub](https://github.com/Fenng/tech-doc-style-chinese.git) | 手动 diff 同步 |
| [to-issues](skills/to-issues/) | Break a plan, spec, or PRD into independently-grabbable issues on the project issue tracker usi… | [GitHub](https://github.com/mattpocock/skills) | 手动 diff 同步 |
| [to-prd](skills/to-prd/) | Turn the current conversation context into a PRD and publish it to the project issue tracker. U… | [GitHub](https://github.com/mattpocock/skills) | 手动 diff 同步 |
| [triage](skills/triage/) | Triage issues through a state machine driven by triage roles. Use when user wants to create an… | [GitHub](https://github.com/mattpocock/skills) | 手动 diff 同步 |
| [ttdbl2-unity-prefab-view-builder](skills/ttdbl2-unity-prefab-view-builder/) | Build or adapt Unity uGUI prefabs and matching Lua Views for the ttdbl2_unity client. Use when… | 内部 | 本地维护 |
| [unity-mcp-skill](skills/unity-mcp-skill/) | Orchestrate Unity Editor via MCP (Model Context Protocol) tools and resources. Use when working… | 第三方 | 手动 diff 同步 |
| [web-novel-downloader](skills/web-novel-downloader/) | Use this skill when the user gives a web novel name (or a chapter-list URL) and wants to downlo… | 自制 | 本地维护 |
| [xdoa-skill](skills/xdoa-skill/) | 用于 XDOA CLI 安装配置、升级指引、能力路由和 OA 任务执行规划。当用户想安装或升级 xdoa、了解 xdoa 能做什么、判断应使用哪类 XDOA 工作流，或通过 xdoa 处理公… | 内部 | 本地维护 |
| [zoom-out](skills/zoom-out/) | Tell the agent to zoom out and give broader context or a higher-level perspective. Use when you… | 自制 | 本地维护 |
<!-- SKILLS_TABLE_END -->

## 来源与同步策略

每个 skill 的来源记录在 [`skills-manifest.json`](skills-manifest.json)。建议使用以下分类：

| 类型 | 含义 |
|---|---|
| `custom` | 自制或主要由本地维护的 skill |
| `github` | 来自 GitHub 仓库的 skill |
| `web` | 来自网页、skills 目录站点或非 GitHub 来源 |
| `third-party` | 第三方来源，但原始 URL 尚未完全确认 |
| `internal` | 内部项目或内部系统相关 skill |

同步策略建议：

| 策略 | 含义 |
|---|---|
| `local` | 本地维护，不从上游自动同步 |
| `manual-diff` | 有上游来源，但同步前必须先 diff，再人工合并 |
| `script` | 可用脚本同步 |
| `git-subtree` | 使用 git subtree 跟踪上游 |

当前建议先使用 **vendored copy + manifest + manual diff**：第三方 skill 复制到本仓库中，记录上游 URL 和本地改动说明；需要更新时先拉取上游到临时目录，diff 后再合并，避免覆盖本地适配。

当前仍需补充原始来源的第三方条目：`hatch-pet`、`pdf`、`unity-mcp-skill`。补齐后把它们从 `third-party` 改为更准确的 `github` / `web`，并填入 `source`。

## 新增 skill 流程

1. 在 `skills/<skill-name>/` 下添加 `SKILL.md`。
2. 如果需要脚本或参考资料，放入该 skill 目录下的 `scripts/`、`references/` 或 `agents/`。
3. 在 `skills-manifest.json` 中登记来源、更新策略和备注。
4. 运行 README 生成脚本：

   ```bash
   python3 scripts/generate-readme.py
   ```

5. 检查 README 中的 Skill 列表是否正确。

## 更新第三方 skill

建议流程：

1. 从 `skills-manifest.json` 找到 `source`。
2. 将上游内容拉到临时目录。
3. 与本仓库中的 `skills/<skill-name>/` 做 diff。
4. 手动合并需要的变更。
5. 更新 manifest 中的备注，例如上游 commit、同步日期或本地改动说明。
6. 运行：

   ```bash
   python3 scripts/generate-readme.py
   ```

不要直接用上游内容覆盖本地 skill，除非确认该 skill 没有本地适配。

## 维护命令

常用检查命令：

```bash
# 重新生成 README 中的 Skill 表格
python3 scripts/generate-readme.py

# 检查 manifest 覆盖、SKILL.md frontmatter、README 表格是否最新
python3 scripts/audit-skills.py

# 检查 JSON 格式
python3 -m json.tool skills-manifest.json >/dev/null
```

`audit-skills.py` 会检查：

- `skills/` 下每个有效 skill 都已登记到 `skills-manifest.json`。
- manifest 中没有指向不存在 skill 的多余条目。
- 每个 `SKILL.md` 都有 `name` 和 `description` frontmatter。
- README 生成区块与当前 skill/manifest 状态一致。

## 维护约定

- `SKILL.md` 是识别 skill 的必要文件；没有 `SKILL.md` 的目录不会出现在 README 表格中。
- 第三方来源必须尽量记录 `source`、license 和本地改动说明。
- README 的 Skill 表格由脚本生成，不要手动编辑标记区块内的内容。
- 对内部项目相关 skill，避免把敏感链接、token 或账号信息写入公开文档。
- `.DS_Store`、下载产物、虚拟环境等本地文件不应提交。

## 兼容性说明

- `SKILL.md`、`scripts/`、`references/`、`requirements.txt` 通常可被 Claude Code 和 Codex 共用。
- `agents/openai.yaml` 仅 Codex 使用，Claude Code 会忽略该目录。
- 推荐使用相对路径和 skill 内部路径，避免绑定到某台机器的绝对路径。
