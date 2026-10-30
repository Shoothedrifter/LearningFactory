# Learning Factory Skill 改造实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 learning-factory 从 PyPI CLI 改造为 GitHub 仓库分发的宿主级 Agent Skill（Claude Code + Codex 双适配），用户零配置（无 API Key、无模型参数）。

**Architecture:** Python 引擎（ReAct/LLM/MCP）退役冻结；方法论（五份提示词）改写为 SKILL.md + references 角色卡，编排归还宿主；html_builder 抽取为独立脚本（PEP 723 + Python 3.9 兼容 + pygments 可选降级）；双路径分发（`.claude-plugin/` plugin + `.agents/skills/` 通用路径经 symlink 单实体）。

**Tech Stack:** Agent Skills 开放标准（SKILL.md frontmatter 6 字段）、Python 3.9+（stdlib + markdown 硬依赖 + pygments 可选）、pytest（全 mock）、Claude Code plugin 机制（plugin.json + marketplace.json）。

**Spec:** [docs/superpowers/specs/2026-10-30-skill-adaptation-design.md](../specs/2026-10-30-skill-adaptation-design.md) —— 本计划的决策依据，执行者须同时阅读 spec（尤其 §2 判断表 J1–J12、§6 各缺口方案、§9 风险表）。

## Global Constraints

- SKILL.md frontmatter 只允许 6 个标准字段：`name` / `description` / `license` / `compatibility` / `metadata` / `allowed-tools`（spec C1）
- SKILL.md 正文 < 500 行；细节下沉 `references/`（spec C2）
- 文件引用用相对路径；`${CLAUDE_SKILL_DIR}` 只能作为 Claude Code 用户的补充写法出现，不得是唯一手段（spec C3）
- 脚本非交互（无 TTY 提示）、幂等、有 `--help`、报错信息可行动（spec C4）
- 产物规范单一事实源：SKILL.md Output Format 节；脚本常量必须与之一致（spec C5）
- 脚本 Python 3.9+ 语法兼容（spec J7）；v1 仅支持 macOS/Linux（spec J8）
- skill 全部文件供应商中立：不出现 GLM / 智谱 / bigmodel 等字样（沿用 guard 测试精神）
- 产物语言要求：简体中文（代码、命令与专有名词保留原文），写进 SKILL.md（spec D 系决策）
- 测试全 mock、无真实网络调用（项目现状）
- commit 信息用简体中文、不出现繁体、不加 Co-author；**commit 前须有用户对本计划的批准（批准计划 = 批准计划内各 commit 步骤）**
- CLI 代码（`learning_factory/`）冻结：本计划不修改其行为，仅测试文件的 import 指向新脚本

## Review Focus

spec 隐含但各任务测试未直接覆盖、最可能咬到使用者的五类输入（每条已钉到归属任务）：

1. **skill 文件改名失联**——SKILL.md 引用的 references 文件被重命名后宿主激活时读不到 → Task 3 `test_references_exist` 扫描 SKILL.md 中所有相对路径引用并断言文件存在
2. **产物名漂移**——SKILL.md 与脚本对四产物名各改各的，HTML 聚合漏产物 → Task 3 `test_artifact_names_consistent` 双向断言
3. **中文触发不命中**——用户说「帮我制定学习计划」但 description 无中文触发词 → Task 2 `test_description_bilingual_triggers` 断言 description 同时含 `learning plan` 与 `学习`
4. **依赖缺失时静默崩**——无 pygments/markdown 环境下报错不可行动 → Task 1 降级测试与 `test_missing_markdown_error_actionable`（断言 stderr 含 `pip install markdown`）
5. **旧 Python 语法炸**——macOS 系统 Python 3.9.6 运行 PEP 604 注解直接 TypeError → Task 1 本机 `/usr/bin/python3` 实跑验证步骤

---

### Task 1: 抽取 build_html.py 为 skill 脚本（3.9 兼容 + PEP 723 + pygments 可选）

**Files:**
- Create: `.agents/skills/learning-factory/scripts/build_html.py`（自 `learning_factory/html_builder.py` 复制后定点改写）
- Create: `.agents/skills/learning-factory/scripts/templates/learning_page.html`（自 `learning_factory/templates/learning_page.html` 原样复制）
- Modify: `tests/conftest.py`（新增 `build_html_module` fixture）
- Modify: `tests/test_html_builder.py`、`tests/test_cli_build.py`（import 与模块加载改为新脚本）
- Test: `tests/test_skill_script.py`（新建）

**Interfaces:**
- Consumes: 原 `html_builder.py` 的全部公开行为（52+23 项既有断言不变，仅换加载方式）
- Produces:
  - 模块常量 `ARTIFACT_NAMES`（四产物名，沿用原值）、`HAS_PYGMENTS: bool`、`SCRIPT_VERSION: str = "1.0.0"`
  - 函数签名沿用原模块：`collect_artifacts` / `build_html` / `prune_factory_root` / `main`
  - `tests/conftest.py` 提供 session 级 fixture `build_html_module`：用 `importlib.util.spec_from_file_location` 从仓库根 `.agents/skills/learning-factory/scripts/build_html.py` 加载（供迁移测试与新测试共用）
  - `tests/conftest.py` 另提供函数级 fixture `build_html_module_reload`：先由测试用 monkeypatch 篡改 `sys.modules`，再强制重新加载脚本模块并返回（专供降级/报错测试观察导入期行为）

- [ ] **Step 1: 写失败测试（新行为：pygments 降级 + markdown 报错可行动）**

新建 `tests/test_skill_script.py`，三个测试：

```python
def test_degrades_without_pygments(monkeypatch, build_html_module_reload):
    """缺 pygments 时模块可加载、HAS_PYGMENTS 为 False、代码示例渲染为纯文本不报错"""
    # monkeypatch 将 sys.modules 中 pygments / pygments.lexers / pygments.formatters 置 None
    # 经 fixture 重新加载模块后：HAS_PYGMENTS is False
    # 对含代码示例的临时产物目录调 build_html，断言输出 HTML 含 <pre> 且构建成功

def test_missing_markdown_error_actionable(monkeypatch, build_html_module_reload, capsys, tmp_path):
    """缺 markdown 时退出码非 0 且 stderr 含 pip install markdown 指引"""
    # monkeypatch sys.modules["markdown"] 为 None 后重新加载并调 main([str(tmp_path)])
    # 断言 SystemExit 且输出含 "pip install markdown"

def test_pep723_header_present():
    """脚本头部含 PEP 723 内联依赖声明且列出的依赖正确"""
    # 读脚本文本前 30 行，断言含 "# /// script" 与 "markdown"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_skill_script.py -v`
Expected: FAIL（脚本文件不存在）

- [ ] **Step 3: 复制并定点改写脚本**

`cp learning_factory/html_builder.py .agents/skills/learning-factory/scripts/build_html.py`（模板同法复制），然后只做四处定点改写：

1. 头部加 `from __future__ import annotations` 与 PEP 723 块（`# /// script`，`dependencies = ["markdown", "pygments"]`）
2. pygments 导入改 try/except，置 `HAS_PYGMENTS`；高亮渲染分支在 `HAS_PYGMENTS is False` 时输出纯 `<pre>` 代码块（markdown 为硬依赖，缺失时 `main` 打印含 `pip install markdown` 的指引后非零退出）
3. 删除 `importlib.metadata` 版本获取块，页脚版本改用常量 `SCRIPT_VERSION = "1.0.0"`
4. `TEMPLATE_PATH` 保持 `Path(__file__).parent / "templates" / "learning_page.html"` 相对定位（目录结构已随复制保持，验证即可）

- [ ] **Step 4: conftest fixture + 迁移两个既有测试文件**

`tests/conftest.py` 加 `build_html_module`（session 级，spec 如上接口）；`test_html_builder.py` / `test_cli_build.py` 中对 `learning_factory.html_builder` 的 import 与属性访问改为 fixture 模块（断言一律不动）。

- [ ] **Step 5: 跑全部相关测试通过**

Run: `.venv/bin/python -m pytest tests/test_skill_script.py tests/test_html_builder.py tests/test_cli_build.py -v`
Expected: PASS（75 项迁移 + 3 项新增）

- [ ] **Step 6: macOS 系统 Python 3.9 实跑验证（Review Focus #5）**

Run: `/usr/bin/python3 .agents/skills/learning-factory/scripts/build_html.py --help && /usr/bin/python3 .agents/skills/learning-factory/scripts/build_html.py Learning-Factory/learning-kubernetes --output /tmp/lf-39-check`
Expected: 帮助正常打印；真实产物目录构建出 HTML（若该目录不存在，任选一个 `Learning-Factory/` 下的现存包）

- [ ] **Step 7: Commit**

```bash
git add .agents/skills/learning-factory/scripts/ tests/test_skill_script.py tests/conftest.py tests/test_html_builder.py tests/test_cli_build.py
git commit -m "抽取 HTML 构建器为 skill 独立脚本：3.9 兼容、PEP 723、pygments 可选降级"
```

### Task 2: SKILL.md 与 references 角色卡

**Files:**
- Create: `.agents/skills/learning-factory/SKILL.md`（英文成稿，frontmatter 精确值见 Step 1）
- Create: `.agents/skills/learning-factory/references/docs-researcher.md`（改写自 `learning_factory/prompts/docs_researcher.md`）
- Create: `.agents/skills/learning-factory/references/web-researcher.md`（改写自 `learning_factory/prompts/web_researcher.md`）
- Create: `.agents/skills/learning-factory/references/repo-analyzer.md`（改写自 `learning_factory/prompts/repo_analyzer.md`，工具段重写）
- Create: `.agents/skills/learning-factory/references/file-writer.md`（改写自 `learning_factory/prompts/file_writer.md`，去分块化）
- Create: `.agents/skills/learning-factory/references/progressive-learning.md`（原样复制自 `learning_factory/skills/learning-a-tool/references/progressive-learning.md`）
- Modify: `tests/test_no_glm_names.py`（扫描范围扩展到 `.agents/skills/`）
- Test: `tests/test_skill_package.py`（新建，本任务只写 frontmatter/行数/触发词三项，Task 3 增补）

**Interfaces:**
- Consumes: spec §5.2（frontmatter 精确值）、§5.3（六阶段流程骨架）、§6.1（Hard Rules + DoD 四条）、§6.2（并行降级措辞）、§6.3（repo 工具策略）、§6.4（file-writer 简化范围）
- Produces: 五级中文标题固定为常量列表（Task 3 一致性测试用）：`概览与动机` / `安装与 Hello World` / `核心概念` / `实战模式` / `进阶方向`；四产物名与 Task 1 `ARTIFACT_NAMES` 相同

- [ ] **Step 1: 写失败测试（frontmatter 合规 / 行数 / 双语触发 / 供应商中立）**

新建 `tests/test_skill_package.py`：

```python
FRONTMATTER_STANDARD_FIELDS = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}

def test_frontmatter_standard_fields_only():
    # 解析 SKILL.md frontmatter（--- 之间 YAML），断言字段集合 ⊆ FRONTMATTER_STANDARD_FIELDS 且含 name、description

def test_skill_md_under_500_lines():
    # 断言 SKILL.md 总行数 < 500

def test_description_bilingual_triggers():   # Review Focus #3
    # 断言 description 同时包含 "learning plan"（不区分大小写）与 "学习"

def test_skill_files_vendor_neutral():
    # 断言 .agents/skills/ 下全部文本文件不含 "bigmodel"（guard 精神前置自查）
```

同步骤扩展 `tests/test_no_glm_names.py` 的文件收集范围，纳入 `.agents/skills/**/*.md` 与 `.agents/skills/**/*.py`。

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_skill_package.py tests/test_no_glm_names.py -v`
Expected: FAIL（SKILL.md 不存在）

- [ ] **Step 3: 成稿 SKILL.md（英文，结构锁定）**

frontmatter 精确值（spec §5.2 + J8 compatibility）：

```yaml
---
name: learning-factory
description: Generate a complete Chinese learning package (5-level learning path, curated resources, runnable code examples, single-file interactive HTML) for any technology topic. Use when the user asks to create a learning plan / study path / 学习计划 for a tool, framework, or technology.
license: MIT
compatibility: macOS or Linux with bash and python3 (3.9+); Windows not supported in v1; uv recommended for script dependencies.
---
```

正文章节骨架（顺序固定）：① Hard Rules（置顶：三路研究缺一不可、交叉印证后才落盘、产物简体中文强制且代码/命令/专有名词保留原文、一文件一任务）→ ② 六阶段流程 Plan / Research / Synthesize / Write / Build / Verify（Research 阶段用 spec §6.2 的宿主无关降级措辞；Build 阶段给 `uv run scripts/build_html.py <dir>` 优先、`python3 scripts/build_html.py <dir>` 回退、失败时提示 `pip install markdown pygments`）→ ③ Output Format（目录树 `Learning-Factory/learning-{topic}/`、四产物、五级中文标题、code-examples 三子目录约定）→ ④ Definition of Done（四条自检项，要求宿主在最终回复逐项确认，spec §6.1 原文）。全篇相对路径引用 references 与 scripts。

- [ ] **Step 4: 成稿五个 references 文件**

改写规则：保留原提示词的角色/流程/输出格式结构；删除 OpenAI function-calling 特有表述与工具名硬编码，改为宿主无关描述。两个特殊文件：`repo-analyzer.md` 工具段按 spec §6.3 重写（首选 `git clone --depth 1 <repo>` 到系统临时目录后用文件工具读；备选宿主网页抓取；保留「至多精读 4–5 个关键文件」；研究完删除克隆目录）；`file-writer.md` 按 spec §6.4 删 1400/1500 分块工作流，保留简体中文强制、先读后写、转义意识。`progressive-learning.md` 直接 `cp`。

- [ ] **Step 5: 跑测试通过**

Run: `.venv/bin/python -m pytest tests/test_skill_package.py tests/test_no_glm_names.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add .agents/skills/learning-factory/SKILL.md .agents/skills/learning-factory/references/ tests/test_skill_package.py tests/test_no_glm_names.py
git commit -m "新增 learning-factory skill：SKILL.md 主流程与五个研究角色卡"
```

### Task 3: skill 包完整性守护（引用存在 + 产物名一致）

**Files:**
- Modify: `tests/test_skill_package.py`（增补三项）
- Test: 同文件

**Interfaces:**
- Consumes: Task 1 的 `build_html_module.ARTIFACT_NAMES`；Task 2 的 SKILL.md 与五级标题常量列表
- Produces: 无（纯守护测试）

- [ ] **Step 1: 写失败测试**

```python
FIVE_LEVEL_TITLES = ["概览与动机", "安装与 Hello World", "核心概念", "实战模式", "进阶方向"]

def test_references_exist():            # Review Focus #1
    # 提取 SKILL.md 与各角色卡中的相对路径引用（references/xxx.md、scripts/xxx），
    # 断言每个引用的文件在 skill 目录下真实存在

def test_artifact_names_consistent():   # Review Focus #2
    # 断言 SKILL.md 文本包含 build_html_module.ARTIFACT_NAMES 的每个产物名
    # 且 ARTIFACT_NAMES 集合 == {"README.md", "resources.md", "learning-path.md"} ∪ code-examples 约定

def test_five_level_titles_consistent():
    # 断言 FIVE_LEVEL_TITLES 每个标题同时出现在 SKILL.md 与 progressive-learning.md 中
```

- [ ] **Step 2: 跑测试确认失败（或核对后通过）**

Run: `.venv/bin/python -m pytest tests/test_skill_package.py -v`
Expected: 新增三项先 FAIL（引用提取或一致性缺口），据失败点修正 SKILL.md / 脚本常量至 PASS——若 SKILL.md 成稿时已满足，测试直接 PASS 亦可接受（守护意义在防未来漂移）

- [ ] **Step 3: Commit**

```bash
git add tests/test_skill_package.py .agents/skills/learning-factory/
git commit -m "skill 包完整性守护：引用存在性与产物规范一致性测试"
```

### Task 4: 分发接线（plugin.json + marketplace.json + symlink）

**Files:**
- Create: `.claude-plugin/plugin.json`
- Create: `.claude-plugin/marketplace.json`
- Create: `skills/learning-factory`（symlink → `../.agents/skills/learning-factory`）
- Test: `tests/test_skill_package.py`（增补两项）

**Interfaces:**
- Consumes: Task 1/2 的 skill 实体目录
- Produces: plugin 名 `learning-factory`、marketplace 名 `LearningFactory`（README 与验收命令引用，精确值锁定）

- [ ] **Step 1: 写失败测试**

```python
def test_plugin_and_marketplace_json_valid():
    # 两个 JSON 可解析；plugin.json 含 name == "learning-factory" 与 version；
    # marketplace.json 含 name == "LearningFactory" 且 plugins[0] 指向的路径存在

def test_skills_symlink_valid():
    # 断言 skills/learning-factory 是 symlink 且指向的目标目录存在、内含 SKILL.md
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_skill_package.py -v`
Expected: FAIL（文件不存在）

- [ ] **Step 3: 创建三个分发文件**

`plugin.json`：`{"name": "learning-factory", "description": "Generate complete Chinese learning packages with 5-level paths, resources, code examples and single-file interactive HTML.", "version": "1.0.0", "author": {"name": "Shoothedrifter"}}`
`marketplace.json`：`{"name": "LearningFactory", "owner": {"name": "Shoothedrifter"}, "plugins": [{"name": "learning-factory", "source": "./"}]}`
symlink：`ln -s ../.agents/skills/learning-factory skills/learning-factory`

- [ ] **Step 4: 跑测试通过 + 本机 plugin 校验**

Run: `.venv/bin/python -m pytest tests/test_skill_package.py -v && claude plugin validate ./`
Expected: PASS；若本机 Claude Code 版本 ≥ 2.1.233 则 validate 通过（版本不足时记录结果，不阻塞——CI 不依赖它）

- [ ] **Step 5: Commit**

```bash
git add .claude-plugin/ skills/
git commit -m "接入双路径分发：plugin 市场清单与 skills 符号链接"
```

### Task 5: 仓库文档收尾（README / AGENTS.md / CI 检查）

**Files:**
- Modify: `README.md`、`README.en.md`（安装章节重写为三态；删除「配置」章节；新增 Codex 沙箱说明一行）
- Modify: `AGENTS.md`（增补「skill 形态与 CLI 冻结」小节：指向 spec、说明 J1/J2/J9 策略）
- Modify: `git 状态`：正式提交 AGENT.md → AGENTS.md 未提交重命名（内容无变化，`git add AGENTS.md AGENT.md` 记录删除）
- Verify: `.github/workflows/ci.yml`（确认 pytest 自动收集新测试，无路径排除则不改）

**Interfaces:**
- Consumes: Task 4 的安装命令精确值（`/plugin marketplace add Shoothedrifter/LearningFactory` → `/plugin install learning-factory@LearningFactory`；Codex 经 `$skill-installer` 或复制 `.agents/skills/learning-factory/` 到 `~/.agents/skills/`）
- Produces: 无

- [ ] **Step 1: 重写两个 README 的安装/配置/运行章节**

安装三态表照 spec §6.8 精确值；删除环境变量表与 .env 说明；「运行」章节替换为 skill 用法示例（一句话触发 + DoD 说明）；开发与测试章节保留（pytest 数量更新为新总数）；顶部新增一行「推荐通过 Agent Skill 使用（零配置），CLI 已冻结于 0.3.0」。

- [ ] **Step 2: AGENTS.md 增补 + 提交重命名**

增补小节内容要点：仓库双形态（skill 主产品 + CLI 冻结）、skill 实体在 `.agents/skills/learning-factory/`、`skills/` 是 Claude Code plugin 扫描路径的 symlink、75 项 html 测试已迁移至 skill 脚本。同 commit 里完成 AGENT.md 删除记录。

- [ ] **Step 3: 验证**

Run: `.venv/bin/python -m pytest -q && grep -c "plugin marketplace add" README.md README.en.md`
Expected: 全量测试 PASS（233 + 新增 ≈ 240+ 项）；两个 README 各命中安装命令

- [ ] **Step 4: Commit**

```bash
git add README.md README.en.md AGENTS.md AGENT.md
git commit -m "文档转向 skill 主形态：安装三态、移除配置章节、AGENTS.md 说明冻结策略"
```

### Task 6: 双宿主冒烟验收（人工 checklist，对应 spec §7 A1–A5 与 §9 R1/R2）

**Files:**
- 无代码变更；产出验收记录 `docs/superpowers/plans/2026-10-30-skill-acceptance.md`（逐项勾选 + 失败记录）

**Interfaces:**
- Consumes: Task 1–5 全部产物
- Produces: 验收结论（A1–A5 状态）；R1/R2 的实测结论决定是否触发 spec §9 缓解方案（symlink 失效 → 双份生成；Codex 路径不可解析 → 措辞调整）

- [ ] **Step 1: Claude Code 验收（A1 + R1 + R3/R5 冒烟广度）**

干净 profile 装 plugin：`claude plugin marketplace add Shoothedrifter/LearningFactory` → `claude plugin install learning-factory@LearningFactory`（本机未推送时先用 `claude --plugin-dir ./` 等价验证）；确认 symlink 经安装链路后 skill 仍被发现（R1）。冒烟覆盖（spec §9 R3/R5）：3 个主题（Docker / PyTorch / 一个冷门主题）各产包核对 DoD 四项与 HTML 双击可开；另测 5 种问法（如「学习计划」「study path」「我想入门 X」「帮我学 X」「create a learning plan for X」）确认触发；全程无 API Key 要求（A3）。

- [ ] **Step 2: Codex 验收（A2 + R2 + 同广度）**

复制 `.agents/skills/learning-factory/` 到 `~/.agents/skills/`；真实项目里同场景触发（同 3 主题 + 5 问法）；核对产物与 DoD；确认脚本路径被正确解析（含 `uv run` 与 `python3` 回退两条）与沙箱批准项与 README 说明一致（R2）。

- [ ] **Step 3: 记录与判定**

A3（全程零 Key）、A4（CI 绿）、A5（README 步骤照做可复现）逐项记录；双宿主各确认对 `.claude-plugin/` 与 `.agents/` 对方目录无副作用（R6）；任何 FAIL → 按对应缓解方案回补任务或修订 spec，未全过不对外宣传（spec §8 约定）。

- [ ] **Step 4: Commit 验收记录**

```bash
git add docs/superpowers/plans/2026-10-30-skill-acceptance.md
git commit -m "双宿主冒烟验收记录：Claude Code 与 Codex 实测结论"
```
