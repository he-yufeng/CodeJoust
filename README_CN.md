# CodeJoust

[![PyPI](https://img.shields.io/pypi/v/codejoust.svg)](https://pypi.org/project/codejoust/)
[![Python](https://img.shields.io/pypi/pyversions/codejoust.svg)](https://pypi.org/project/codejoust/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**让 AI 编程助手比赛解同一个 bug。按测试通过率、diff 大小、成本、耗时自动打分，合并胜者的 patch。**

English → [README.md](README.md)

---

同样的模型，换个壳，表现完全不同。第三方实测：同样的 Claude Sonnet，通过 Claude Code 跑 benchmark 得 77 分，通过 Cursor 跑得 93 分——15 分的差距全在工具/harness 上，和模型本身没关系。

所以"哪个 AI 编程助手适合我的任务"不是模型问题，而是**任务级别的经验问题**。只能实测。

CodeJoust 一条命令同时把同一个任务扔给 Claude Code、aider（很快会支持 Codex / Cursor CLI / Gemini CLI），每个 agent 在独立的 `git worktree` 里干活，跑完自动打分，把胜者的 patch 递到你手上。

## 为什么不直接开三个终端？

大部分人就是这么干的，也正因为如此，大部分人从来不真的横向对比过——同时开三个 agent、等它们跑完、逐个看 diff、算 token 数，太麻烦，于是挑一个就用了。

CodeJoust 把这一小时压缩成一条命令：

```bash
codejoust run "fix the off-by-one in Scheduler.next_fire" \
  --agents claude-code,aider,codex --test "pytest tests/test_scheduler.py"
```

你会得到：

- 终端表格，按 测试通过率 → 成本 → diff 大小 → 耗时 的顺序排名
- 单文件 HTML 报告，每个 agent 的完整 diff 并排展示
- 每个 agent 一个 `.patch` 文件，`git apply` 就能合并

## 安装

```bash
pip install codejoust
```

还需要装你想让它们比赛的 agent CLI。想拉哪几个就装哪几个：

```bash
# Claude Code
npm install -g @anthropic-ai/claude-code

# aider
pip install aider-chat

# OpenAI Codex CLI
npm install -g @openai/codex
```

按每个 CLI 自己的要求配好 API Key（`ANTHROPIC_API_KEY`、`OPENAI_API_KEY` 等）——CodeJoust 只是调起子进程，你原本怎么用它们就怎么用。

## 快速上手

```bash
cd ~/code/my-project

codejoust run "给 deploy 命令加一个 --dry-run 开关"
```

你会看到：

```
─────────── CodeJoust — 2 agents ────────────
task:   给 deploy 命令加一个 --dry-run 开关
repo:   /Users/you/code/my-project
agents: claude-code, aider

                  CodeJoust — 给 deploy 命令...
  #  agent         status    diff        tests    cost      time
★ 1  claude-code   success   +38/-2      8/8      $0.028    71.3s
  2  aider         success   +21/-1      7/8      $0.019    55.7s

winner: claude-code
  — 应用胜者 patch：cat .codejoust/runs/.../claude-code.patch | git apply

report: /Users/you/code/my-project/.codejoust/runs/20260424-222310/report.html
```

所有产物都放在 `.codejoust/runs/<timestamp>/` 下：

| 文件 | 用途 |
| --- | --- |
| `report.html` | 单文件 HTML 报告，并排 diff，可分享 |
| `session.json` | 结构化的运行数据，方便脚本化和 CI |
| `<agent>.patch` | 每个 agent 的变更，`git apply` 应用 |
| `logs/<agent>/*.log` | 每个 CLI 的原始 stdout/stderr |

## 打分规则

按这个优先级打：

1. **测试通过率**（`tests_passed / tests_total`）。自动识别 `pytest` / `npm test`，也可以用 `--test` 手动指定。
2. **成本**（美元）。越低越好。直接从每个 CLI 自己的 usage 输出解析。
3. **Diff 大小**（新增 + 删除行数）。越小越好——改动小的方案一般更稳。
4. **耗时**。最后的 tie-breaker。

**严格偏序**：只要第一项就分出胜负就不看后面的了。比如 Claude Code 过 8/8，aider 过 7/8，即使 aider 更便宜也是 Claude Code 赢——正确性第一。

LLM-as-judge 打分（主观代码质量）放到 v0.2，通过 `--judge` 开启。当前版本坚持纯客观指标，好处是可复现、成本可控。

## Agents

```bash
codejoust agents
#   claude-code    cli: claude
#   aider          cli: aider
#   codex          cli: codex
```

v0.1.1 支持 Claude Code、aider、OpenAI Codex CLI。以下还在路线图上：

- Gemini CLI（`gemini -p`）
- Cursor CLI（`cursor-agent`）——CLI 本身还在快速迭代，标记为 experimental
- OpenHands（`openhands --headless`）

每个 adapter 约 50 行代码，欢迎 PR。

## CLI 参数

```
codejoust run TASK [OPTIONS]

  -a, --agents TEXT      逗号分隔 agent 列表。默认：claude-code,aider
  -r, --repo DIR         仓库根目录。默认：当前目录
      --timeout INT      每个 agent 的超时（秒）。默认：600
      --test CMD         测试命令。默认：自动探测 pytest / npm test
      --model NAME       给每个 agent 统一传的 model 覆盖
      --keep-worktrees   运行结束后保留 worktree，方便手动检查
      --html / --no-html 是否写 report.html。默认：开
      --open             跑完后自动在浏览器打开报告
```

## 对比同类工具

| 项目 | 能做什么 | 缺什么 |
| --- | --- | --- |
| **CodeJoust**（本项目） | CLI、并行多 agent、自动打分（tests+cost+diff）、HTML 报告 | LLM-as-judge 放 Phase 2 |
| [Claude Squad](https://github.com/smtg-ai/claude-squad)（7k★） | tmux + worktree session 管理 | 没打分、不对比 diff，纯手动 |
| [parallel-code](https://github.com/johannesjo/parallel-code)（544★） | 并行多 agent + diff viewer | 没打分、没接测试 |
| [Cursor 3 `/best-of-n`](https://cursor.com/changelog/3-0) | Cursor 内部的 best-of-N | 闭源、锁 IDE、收费、不支持外部 agent |
| [GitHub Agent HQ](https://github.blog/news-insights/company-news/welcome-home-agents/) | GitHub 云上的多 agent | 闭源、收费、必须上云 |
| [Terminal-Bench](https://www.tbench.ai/) / SWE-bench | 固定 benchmark 横评 | 不能扔自己的 issue |
| [CodeClash](https://github.com/CodeClash-ai/CodeClash) | 固定 arena 的 LLM 锦标赛（BattleSnake、扑克等） | 不能跑你自己的仓库 |

CodeJoust 填的那个空位：**开源、CLI 优先、真跑多家 agent（不是同一 IDE 多模型）、自动打分、扔自己的 repo**。

## 常见问题

**需要联网 / 信用卡吗？**
CodeJoust 本身不联网，只调起你本地的 agent CLI，API Key 用你自己的。

**会不会把 API 额度烧爆？**
每个 agent 一个任务只跑一次，默认 `--timeout 600` 兜底。Token 数和花费每次都打印，一眼看得到。

**能同时跑两个以上吗？**
可以：`--agents claude-code,aider,codex`。每个在独立 worktree 里，互不干扰。注意各家 API 的 rate limit。

**Windows 能用吗？**
只在 macOS 和 Linux 上测过。WSL 应该没问题，原生 Windows 没测也不推荐——底层那几个 agent CLI 本身就是 Unix first。

**我没有测试怎么办？**
CodeJoust 仍然会按成本、diff 大小、耗时排名。但最有区分度的信号是测试通过率——想要更准的排名，建议先为你的 bug 写一个能复现的失败测试。

**怎么避免失控烧钱？**
小任务先用 `--timeout 120`。每个 agent 被自己的 API Key 独立限流。CodeJoust 本身不发网络请求。

## 路线图

- **v0.1.0**：Claude Code + aider，客观打分，HTML 报告。
- **v0.1.1**（当前）：OpenAI Codex CLI 适配器——三家同台开箱可用。
- **v0.2**：Gemini CLI 适配器；`--judge` 用 LLM-as-judge 给打平的情况加权；YAML 配置保存常用 agent profile。
- **v0.3**：Cursor CLI + OpenHands 适配器；批量模式（一次跑一组 issue，聚合胜者）；导出 Markdown 方便直接贴 PR 描述。
- **以后**：服务器模式（团队/CI）、公共 arena 排行榜。

**止损判定**：如果 `claude-squad` 或 `parallel-code` 加了内置自动打分，CodeJoust 转型为它们的轻量评分插件，放弃编排层。

## 贡献

Adapter 是最主要的贡献点。看 [`src/codejoust/adapters.py`](src/codejoust/adapters.py)——每个 adapter 是 `AgentAdapter` 的子类，实现 `build_command()` 和 `parse_usage()` 即可。欢迎来 PR 你常用的 agent。

## 协议

MIT，见 [LICENSE](LICENSE)。
