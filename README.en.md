# Learning Factory

**English** | [中文](README.md)

> Still lost deciding where to start with a new technology? Still spending entire evenings hunting for tutorials, vetting resources, and piecing together a learning path?
>
> Hand all of that to **Learning Factory**: name what you want to learn in one sentence, and it produces a ready-to-start learning pack on your local machine — a five-level learning path, curated references, and runnable code examples — automatically bundled into a self-contained interactive HTML page you can open with a double-click.

**Recommended: use it as an Agent Skill (zero config).** Once the skill is installed into your coding agent (Claude Code / Codex / etc.), the coordination, research, and writing are all done by the host agent itself — no API keys or model parameters to configure. The original Python CLI is frozen at 0.3.0 (fatal fixes only; see [below](#cli-frozen-maintenance)).

## What It Does

- **One-sentence request, complete learning pack in Simplified Chinese**: a five-level progressive learning path (概览与动机 → 安装与 Hello World → 核心概念 → 实战模式 → 进阶方向); documents are always written in Simplified Chinese (code, commands, and proper nouns stay in their original language)
- **Three research tracks**: official docs, repository analysis, and community content, cross-validated before anything is written; runs concurrently when the host supports parallel sub-tasks
- **Artifacts written to local disk**: an overview README, a resource roundup, the main learning-path document, and runnable code examples, all written into a local directory
- **Self-contained interactive HTML**: after research, the pack is bundled into a single HTML file (four tabs: overview / learning path / resources / code examples, with every resource link clickable) that opens offline with a double-click
- **Definition of Done self-check**: the host confirms each item — five levels, four artifacts, link provenance, HTML build result — in its final reply

Example structure of a generated learning pack (a real one — learning-kubernetes):

```
Learning-Factory/learning-kubernetes/
├── README.md            # Overview and usage notes
├── resources.md         # All reference links (grouped by source)
├── learning-path.md     # The five-level learning path (~770 lines)
├── code-examples/
│   ├── 01-hello-world/       # nginx-pod.yaml starter example
│   ├── 02-core-concepts/     # deployment / service / configmap-secret — 3 core exercises
│   └── 03-patterns/          # cronjob / ingress / stateful-app — 4 practice patterns
└── learning-kubernetes.html  # Self-contained interactive page (auto-built at the end)
```

Ten packs have been generated locally across different topics (transformer / docker / kubernetes / pytorch / ai-agent / vllm, among others). The learning-kubernetes pack, for instance, aggregates into the self-contained interactive page linked below — four tabs (overview / learning path / resources / code examples), clickable links, works offline:

[![learning-kubernetes interactive page preview](examples/learning-kubernetes-preview.png)](https://shoothedrifter.github.io/LearningFactory/examples/learning-kubernetes.html)

**👉 [Try it live: the full learning-kubernetes interactive page](https://shoothedrifter.github.io/LearningFactory/examples/learning-kubernetes.html)**

The page source lives at [examples/learning-kubernetes.html](examples/learning-kubernetes.html) (a self-contained single file — download it and double-click to view offline).

## Installation (Agent Skill, zero config)

The skill entity lives at `.agents/skills/learning-factory/` in this repository (a single entity shared by both hosts). Pick your host:

| Host | Install |
|------|---------|
| **Claude Code** | Main path: `/plugin marketplace add Shoothedrifter/LearningFactory` → `/plugin install learning-factory@LearningFactory`. Fallback without the marketplace: clone this repo and **copy** `.agents/skills/learning-factory/` to `~/.claude/skills/` (do not clone the whole repo into the skills directory — the nested SKILL.md won't be picked up) |
| **Codex CLI** | Main path: install from this repo's git URL via `$skill-installer` into `~/.agents/skills/`; or manually copy `.agents/skills/learning-factory/` to `~/.agents/skills/` (cloning the whole repo into your project is not recommended — the repo-root AGENTS.md would be loaded as project instructions) |
| **Other hosts** | Any agent that reads `.agents/skills/` (project-level) or `~/.agents/skills/` (user-level) can use it directly (not individually tested in v1) |

Zero config means **no API keys or model parameters** — research, writing, and script execution all go through the host's own model and tools. Sandboxing approvals on first run (network access, temp-directory writes) are host-native interactions; just confirm when prompted.

Script dependencies (markdown / pygments) are declared in the script header via PEP 723: with [uv](https://docs.astral.sh/uv/) installed they're resolved automatically; otherwise the script runs under plain `python3` (3.9+) and prints a one-line install hint if a dependency is missing.

## Usage

After installing, just say it in your host's chat — English or Chinese:

```
Make me a learning plan for Docker
给我制定一份学习 Docker 的学习计划
```

The host follows the SKILL.md workflow: three research passes (official docs / repository / community) → cross-validation → write the four artifacts → bundle a single-file HTML via `scripts/build_html.py` → walk the Definition of Done and confirm each item in the final reply. The resulting HTML opens offline with a double-click: four tabs, every resource link clickable, syntax-highlighted code examples in a nested file tree.

Multi-turn continuation: if you interrupt or the pack is left incomplete, just say "continue the task" (继续完成任务) — the skill's write discipline is read-before-write, so existing content is never destroyed.

## CLI (frozen maintenance)

The Python scaffolding CLI (the `learning-factory` command, with its own multi-agent engine) is **frozen at 0.3.0**: still usable, fatal fixes only, no further evolution — new features land in the skill form only. To keep using it:

```bash
pipx install learning-factory          # from PyPI
```

The CLI requires `LLM_API_KEY` and related environment variables (OpenAI-compatible providers); see the [PyPI page](https://pypi.org/project/learning-factory/) or the "Configuration" section in the 0.3.0 tag's README. CLI-only capabilities such as session persistence (`--resume`) are frozen likewise. The CLI's HTML builder shares its source with the skill script: `learning-factory-build` behaves identically to the skill's `scripts/build_html.py` (including `--prune`).

## More Documentation

Skill design (gap analysis / dual-host adaptation / distribution strategy), architecture (agent collaboration / ReAct loop), the tool system, and the mapping to the original claude_agent_sdk — all in **[AGENTS.md](AGENTS.md)**.

## Development & Testing

```bash
pip install -r requirements-dev.txt
pytest    # 246 tests, fully mocked — no real API key needed
```

Skill-package guard tests (frontmatter compliance, reference existence, artifact-name single source of truth) and script tests (3.9 compatibility, degradation behavior) live under `tests/` as well.

## Notes

- The skill's repository research strategy does a `git clone --depth 1` shallow clone in a system temp directory and deletes it when done — never left in your workspace
- Directories like `Learning-Factory/learning-pytorch/` are generated learning artifacts (already in `.gitignore`, not committed)

## License

[MIT](LICENSE)
