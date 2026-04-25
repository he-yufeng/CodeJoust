# CodeJoust

[![PyPI](https://img.shields.io/pypi/v/codejoust.svg)](https://pypi.org/project/codejoust/)
[![Python](https://img.shields.io/pypi/pyversions/codejoust.svg)](https://pypi.org/project/codejoust/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Pit AI coding agents against the same bug. Score them on tests, diff size, cost, and time. Merge the winner.**

中文 → [README_CN.md](README_CN.md)

---

Same model, different harness. Independent testing found Claude Sonnet scored **77% through Claude Code** but **93% through Cursor** on the same benchmark — a 15-point gap that is pure tooling, not model quality. Which "AI coding assistant" is right for your task is not a model question, it's a **task-level empirical question**.

CodeJoust answers it. One CLI command fires the same task at Claude Code, aider, (soon) Codex, Cursor CLI, Gemini CLI in parallel — each in its own `git worktree` — then auto-grades them and hands you the winning patch.

## Why not just open three terminals?

That's what most people do. It's also why most people never actually benchmark their tools — running three agents, waiting, eyeballing three diffs, manually tallying tokens is work, so they pick one and stick with it.

CodeJoust takes that hour down to one command:

```bash
codejoust run "fix the off-by-one in Scheduler.next_fire" \
  --agents claude-code,aider,codex --test "pytest tests/test_scheduler.py"
```

You get:

- A side-by-side terminal table ranked by test pass-rate → cost → diff size → latency
- A single-file HTML report with each agent's full diff
- One `.patch` file per agent — apply the winner with `git apply`

## Install

```bash
pip install codejoust
```

You'll also need whichever agent CLIs you want to race. Install as many or as few as you like:

```bash
# Claude Code
npm install -g @anthropic-ai/claude-code

# aider
pip install aider-chat

# OpenAI Codex CLI
npm install -g @openai/codex

# Google Gemini CLI
brew install gemini-cli  # or: npm install -g @google/gemini-cli
```

Set the usual API keys in your environment (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, etc.) — CodeJoust just shells out to each CLI, so whatever auth setup you already use keeps working.

## Quickstart

```bash
cd ~/code/my-project

codejoust run "add a --dry-run flag to the deploy command"
```

You'll see:

```
─────────── CodeJoust — 2 agents ────────────
task:   add a --dry-run flag to the deploy command
repo:   /Users/you/code/my-project
agents: claude-code, aider

                  CodeJoust — add a --dry-run flag...
  #  agent         status    diff        tests    cost      time
★ 1  claude-code   success   +38/-2      8/8      $0.028    71.3s
  2  aider         success   +21/-1      7/8      $0.019    55.7s

winner: claude-code
  — git log and merge via: cat .codejoust/runs/.../claude-code.patch | git apply

report: /Users/you/code/my-project/.codejoust/runs/20260424-222310/report.html
```

All artifacts live in `.codejoust/runs/<timestamp>/`:

| file | what |
| --- | --- |
| `report.html` | single-file HTML, side-by-side diffs, shareable |
| `session.json` | structured run data (for scripting and CI) |
| `<agent>.patch` | the agent's changes, apply with `git apply` |
| `logs/<agent>/*.log` | raw stdout/stderr from each CLI |

## How it scores

Four signals, in order:

1. **Test pass ratio** (`tests_passed / tests_total`). Auto-detects `pytest` or `npm test`; override with `--test`.
2. **Cost** (USD). Lower is better. Pulled from each CLI's own usage output.
3. **Diff size** (added + removed lines). Smaller is better — more conservative changes are usually safer.
4. **Wall time**. Tie-breaker.

The first signal where one agent strictly beats another decides the winner. This is intentional: if Claude Code passes 8/8 tests and aider passes 7/8, we don't care that aider was cheaper — test correctness dominates.

LLM-as-judge scoring (subjective code quality) is planned for v0.2 behind `--judge`; for now the scoring is fully objective so it's reproducible and cheap.

## Agents

```bash
codejoust agents
#   claude-code    cli: claude
#   aider          cli: aider
#   codex          cli: codex
#   gemini         cli: gemini
```

v0.2 ships with Claude Code, aider, OpenAI Codex CLI, and Google Gemini CLI. Still on the roadmap:

- Cursor CLI (`cursor-agent`) — flagged experimental until the CLI stabilises
- OpenHands (`openhands --headless`)

Each adapter is ~50 lines. PRs welcome.

## CLI reference

```
codejoust run TASK [OPTIONS]

  -a, --agents TEXT      comma-separated list. default: claude-code,aider
  -r, --repo DIR         repo root. default: current directory
      --timeout INT      per-agent timeout in seconds. default: 600
      --test CMD         test command. default: auto-detect pytest / npm test
      --model NAME       optional model override passed to every agent
      --keep-worktrees   don't clean up worktrees afterwards
      --html / --no-html write report.html. default: on
      --open             open the report in your browser when done
```

## vs. other tools

| Project | What it does | What it doesn't |
| --- | --- | --- |
| **CodeJoust** (this) | CLI, parallel agents, auto-score (tests+cost+diff), HTML report | LLM-as-judge is Phase 2 |
| [Claude Squad](https://github.com/smtg-ai/claude-squad) (7k★) | tmux + worktree session manager | no scoring, no diff comparison — manual |
| [parallel-code](https://github.com/johannesjo/parallel-code) (544★) | parallel runs + diff viewer | no auto-score, no test integration |
| [Cursor 3 `/best-of-n`](https://cursor.com/changelog/3-0) | best-of-N inside Cursor | closed source, IDE-only, paid, no external CLIs |
| [GitHub Agent HQ](https://github.blog/news-insights/company-news/welcome-home-agents/) | multi-agent on GitHub Cloud | closed source, paid, cloud only |
| [Terminal-Bench](https://www.tbench.ai/) / SWE-bench | fixed benchmark evaluation | can't throw your own issue at it |
| [CodeClash](https://github.com/CodeClash-ai/CodeClash) | LLM tournaments on fixed arenas (BattleSnake, Poker) | not for your codebase |

The empty cell CodeJoust fills: **open-source, CLI-first, real agents (not just models), auto-scored, on your own repo**.

## FAQ

**Does it need internet / a credit card?**
Only what the underlying agent CLIs need. CodeJoust itself is offline.

**What about cost blowup?**
Each agent runs once per task. Default `--timeout 600` caps wall time. Tokens and USD are reported per run; you'll see exactly what each task cost.

**Can I run more than two agents at once?**
Yes: `--agents claude-code,aider,codex`. Each runs in its own worktree, fully isolated. Watch your API rate limits.

**Does it work on Windows?**
Tested on macOS and Linux. Windows should work inside WSL; native Windows has not been tested and is unlikely to work cleanly because the agent CLIs themselves are Unix-first.

**What if I don't have tests?**
CodeJoust still ranks by cost, diff size, and wall time. But the really useful ranking signal is test pass-rate — if you can write a single failing test for your bug first, you'll get much better picks.

**How do I stop the project from churning through my API quota?**
Start with `--timeout 120` for small tasks. Each agent is independently rate-limited by its own API key. CodeJoust makes no network calls itself.

## Roadmap

- **v0.1.0**: Claude Code + aider, objective scoring, HTML report.
- **v0.1.1**: OpenAI Codex CLI adapter — three-way races out of the box.
- **v0.2.0** (now): Google Gemini CLI adapter; four agents on the same task.
- **v0.3**: `--judge` for LLM-as-judge tie-breaking, YAML config for reusable agent profiles, Cursor + OpenHands adapters, batch mode, Markdown PR export.
- **later**: server mode for team/CI use, public arena leaderboard.

Kill criteria: if `claude-squad` or `parallel-code` ship built-in auto-scoring, CodeJoust repositions as the lightweight standalone scorer and deprecates its orchestration layer.

## Contributing

Adapters are the main contribution surface. See [`src/codejoust/adapters.py`](src/codejoust/adapters.py) — each adapter is a subclass of `AgentAdapter` with `build_command()` and `parse_usage()`. Open a PR with your agent of choice.

## License

MIT. See [LICENSE](LICENSE).
