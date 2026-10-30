---
name: learning-factory
description: Generate a complete Chinese learning package (5-level learning path, curated resources, runnable code examples, single-file interactive HTML) for any technology topic. Use when the user asks to create a learning plan / study path / 学习计划 for a tool, framework, or technology.
license: MIT
compatibility: macOS or Linux with bash and python3 (3.9+); Windows not supported in v1; uv recommended for script dependencies.
---

# Learning Factory

Generate a complete, self-contained Chinese learning package for any technology topic: a five-level learning path, curated resources, runnable code examples, and a single-file interactive HTML page that bundles everything.

## Hard Rules (non-negotiable)

1. **Three research passes are all mandatory**: official documentation, repository analysis, and community content. Never synthesize from fewer than three.
2. **Cross-validate before writing**: only material confirmed across research passes (or from an authoritative official source) enters the output. Contradictions get flagged, not silently resolved.
3. **Simplified Chinese is mandatory** for all generated documents — headings, body, tables, lists. Code, commands, configuration keys, file paths, error messages, proper nouns, and URLs stay in their original language.
4. **One file per task**: each output file is written as one complete unit. Read before writing when the file may already exist.

## Workflow

### 1. Plan

Confirm the topic with the user. Produce a research work-split across three roles; each role has a card under `references/`:

| Pass | Role card | What it covers |
|------|-----------|----------------|
| Docs | `references/docs-researcher.md` | Official documentation: motivation, install, core concepts, official examples |
| Repo | `references/repo-analyzer.md` | Repository structure, quick start, examples layout |
| Web | `references/web-researcher.md` | Tutorials, videos, comparisons, gotchas |

### 2. Research

If your environment supports spawning parallel sub-tasks, dispatch the three research roles concurrently, each with its role card from `references/` as the sub-task prompt. Otherwise, complete the three research passes sequentially in order: docs → repo → web.

Each pass returns structured findings with source URLs.

### 3. Synthesize

Cross-validate the three result sets: deduplicate, resolve contradictions (prefer official sources), and mark unresolved disagreements explicitly in the output.

### 4. Write

Produce the four artifacts under the Output Format below, following `references/file-writer.md` as the writing discipline (Simplified Chinese mandatory, read-before-write, escape-awareness for code blocks) and `references/progressive-learning.md` as the source of truth for level content requirements.

### 5. Build

Aggregate everything into a single interactive HTML page with `scripts/build_html.py`:

```bash
uv run scripts/build_html.py Learning-Factory/learning-{topic}
```

If `uv` is unavailable, fall back to `python3 scripts/build_html.py <dir>`; if imports fail there, ask the user to run `pip install markdown pygments` and retry (the script header also declares these via PEP 723).

### 6. Verify

Run through the Definition of Done below and confirm each item in your final reply to the user.

## Output Format

Create the folder under `./Learning-Factory/` in the current working directory (a user-specified location overrides this default):

```
Learning-Factory/learning-{topic}/
├── README.md           # 包使用说明：主题、结构、如何开始
├── learning-path.md    # 主内容：五个层级
├── resources.md        # 全部链接，按官方/社区分组
└── code-examples/      # 可运行的示例代码
    ├── 01-hello-world/
    ├── 02-core-concepts/
    └── 03-patterns/
```

`learning-path.md` MUST contain exactly five levels, in this order, with these exact Chinese titles:

1. 概览与动机
2. 安装与 Hello World
3. 核心概念
4. 实战模式
5. 进阶方向

Do not merge, skip, or rename levels.

## Definition of Done

Confirm each item explicitly in the final reply:

- [ ] 五级标题齐全（概览与动机 / 安装与 Hello World / 核心概念 / 实战模式 / 进阶方向）
- [ ] 四产物齐全（README.md / learning-path.md / resources.md / code-examples/）
- [ ] resources.md 中链接均来自本轮研究来源，无编造
- [ ] HTML 构建成功且报告路径
