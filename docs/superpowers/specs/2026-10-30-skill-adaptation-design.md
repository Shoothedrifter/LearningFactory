# 设计文档：learning-factory 改造为宿主级 Skill（Claude Code + Codex 双适配）

日期：2026-10-30
状态：待作者确认（含 12 处「我的判断」待抽查，见 §2.2 与 §2.3；J6–J12 来自独立 reviewer 审读）

## 1. 意图与为什么

当前 learning-factory 以 PyPI CLI（脚手架）分发，用户安装后必须配置 9 个环境变量（API Key、BASE_URL、3 个模型名、MCP 端点等）才能运行——这是采用率的最大摩擦点。

本设计把项目改造为 GitHub 公开仓库分发的 **Agent Skill**：Python 引擎（ReAct 循环、LLM 客户端、MCP 封装）退役，模型/研究工具/子 Agent 编排全部归还宿主（Claude Code、Codex CLI），项目保留两部分核心资产：

1. **方法论**：五个 Agent 提示词（已是独立 Markdown）改写为 SKILL.md + references 角色卡
2. **构建器**：html_builder.py（零 LLM、零网络、零包内依赖）保留为 skill 脚本

用户侧效果：**零配置**——模型用宿主订阅，研究用宿主自带工具，安装即用。

**作者已定决策**：Claude Code 自己当协调者，Python 引擎退役；目标宿主限定 Claude Code 与 Codex CLI，暂不考虑 Cursor 等其他 Agent。

## 2. 决策记录

### 2.1 作者已定（对话中确认）

| 决策 | 内容 |
|---|---|
| D1 | 编排归属：宿主 Agent 当协调者，`learning_factory/` 的 LLM 调用与 ReAct 引擎退役 |
| D2 | 目标宿主：Claude Code + Codex CLI 双适配；Cursor 等其他宿主明确排除在 v1 之外 |
| D3 | 解决的问题：用户不用配置任何模型/API Key |

### 2.2 我的判断（作者审阅时可推翻）

| # | 判断 | 理由 |
|---|---|---|
| J1 | **本仓库转型，不另开新仓库**：仓库根加 `.claude-plugin/plugin.json` 与 `.agents/skills/learning-factory/`，CLI 代码原地保留并冻结 | 不分裂 star/issue 历史；PyPI 老用户文档有处可指；反方案（新开 skill 专用仓库）会带来双仓同步负担 |
| J2 | **CLI 冻结在 0.3.0 转维护模式**：不再加功能，仅修致命 bug；README 引导新用户走 skill 安装 | 双形态同步演进 = 双倍维护；冻结让 skill 成为唯一产品线 |
| J3 | **skill 名 `learning-factory`**（不用现有内置名 learning-a-tool） | 与品牌/仓库名一致；原 learning-a-tool 是包内第三层技能，语境不同 |
| J4 | **SKILL.md 与 references 角色卡用英文写**，产物中文要求（简体）写在指令内 | 现有提示词资产即英文写+中文产物要求；宿主模型对英文指令遵循度更稳；README 面向用户保持中英双语 |
| J5 | **skill 实体文件放 `.agents/skills/learning-factory/`，`skills/learning-factory` 做符号链接指向它**（Claude Code plugin 标准路径经 symlink 指向 Codex 通用路径） | 单一实体避免双份漂移；Claude Code 官方确认 skills 目录支持 symlink；symlink 在 plugin 安装链路中的行为列入待验证清单（§9） |

### 2.3 补充判断（独立 reviewer 审读后定，J6–J12）

| # | 判断 | 理由与背景 |
|---|---|---|
| J6 | **「零配置」的边界 = 不配置 API Key 与模型参数**；宿主原生权限交互（Codex 沙箱批准网络/临时目录写入、Claude Code 工具权限提示）允许存在，README 给 Codex 用户一行前置说明 | 这是所有 coding agent 的常态交互，不违背 D3 的本意（配置复杂度才是痛点）；若禁止一切批准则 §6.3 clone 首选路径与 §6.4 uv 优先策略都要推翻，代价不成比例 |
| J7 | **build_html.py 兼容 Python 3.9+**：抽取时做语法降级改写（`Path \| None` → `Optional[Path]` 等 PEP 604 消除），G3 的「原样保留」修正为「逻辑原样、语法降级」 | reviewer 实测：macOS 自带 `/usr/bin/python3` 为 3.9.6，现代码 dataclass 的 PEP 604 写法在 3.9 直接 TypeError——不改则 G1「安装即用」在默认 Mac 上开箱即炸；降级成本仅几处类型标注 |
| J8 | **v1 不承诺 Windows**：compatibility 字段与 README 明示 macOS / Linux（bash）；symlink 在 Windows 默认 git 检出（`core.symlinks=false`）下失效列为已知限制 | 目标宿主虽跨平台，但作者开发与验收均在 macOS；为 Windows 放弃 J5 单实体方案（改双份生成）得不偿失，未来需要时按 R1 缓解方案升级 |
| J9 | **测试单实体迁移**：75 项 html 测试只测新脚本（迁移后修正 import）；包内 `learning_factory/html_builder.py` 冻结保留（PyPI 0.3.0 用户体验不变）；J2 的致命 bug 例外条款细化为「修复时两处同步修」 | 双跑（参数化测两份实现）增加 CI 成本与夹具复杂度；冻结代码不动即无回归风险，双跑守的是一份永不改变的代码，价值极低 |
| J10 | **Codex 主推 `$skill-installer`（或手动复制 skill 目录）装入 `~/.agents/skills/`，不推荐 clone 整仓到用户项目** | reviewer 指出：clone 整仓会让 Codex 把仓库根 22.9KB、面向本仓库开发者的 AGENTS.md 当作用户项目的项目级指令整体加载，且 tests/ 等全部进入用户工作区——上下文污染 + 噪音 |
| J11 | **Claude Code 主路径为 plugin marketplace；免 marketplace 兜底改为「clone 后复制 `.agents/skills/learning-factory/` 到 `~/.claude/skills/`」** | reviewer 指出原文档 `git clone <repo> ~/.claude/skills/learning-factory` 扫不到嵌套在 `.agents/skills/` 下的 SKILL.md（个人 skills 目录扫描 clone 根），该命令按字面不可用 |
| J12 | **仓库根同时提供 `.claude-plugin/marketplace.json`（单插件最小条目）与 `plugin.json`** | 仅凭 plugin.json 时 `/plugin install learning-factory@LearningFactory` 能否解析取决于宿主版本对单插件仓库的自动识别；加最小 marketplace.json 使两步安装命令确定可跑通，成本一个约 10 行的文件 |

## 3. 目标 / 非目标 / 反目标

### 3.1 目标（v1）

- G1 Claude Code 用户一条命令安装（`/plugin marketplace add` 或 git clone），Codex 用户 clone 到 `.agents/skills/` 或经 `$skill-installer` 装入，均零配置
- G2 双宿主下说一句「帮我制定学习 X 的计划」，产出与现在 CLI 同规格的学习包：五级中文学习路径 + resources.md + README.md + code-examples/ + 单文件交互式 HTML
- G3 HTML 构建器原样保留（含现有 ~75 项测试），skill 内以脚本形式调用
- G4 CI：脚本测试 + skill 格式校验（`claude plugin validate` + `skills-ref validate`）全绿
- G5 README 重写：安装三态（Claude Code / Codex / 通用），配置章节整章删除

### 3.2 非目标（v1 明确不做）

- Cursor / Gemini CLI / OpenCode 等其他宿主适配（结构上不阻碍未来加，但 v1 不测不宣传）
- Notion 工具迁移（宿主用户自配 Notion MCP 即可）
- `server.py` Web 模式（本就标注待修复，随 CLI 一并冻结）
- 多 skill 拆分（v1 单一 skill：learning-factory）
- CLI 与 skill 功能对齐演进（见 J2）

### 3.3 反目标（即使技术可行也不做）

- skill 内捆绑任何 LLM 配置、API Key 读取或自带模型调用——那是回到老问题
- frontmatter 使用 Claude Code 专属字段（`context: fork`、`disable-model-invocation` 等）——会破坏 Codex 兼容；Claude Code 专属增强（如 `${CLAUDE_SKILL_DIR}` 路径写法）只允许以「补充说明」形式出现在正文，不作为唯一手段
- 为追求编排强制力在 skill 里引入可执行编排代码（那就成了第二个小 CLI）

## 4. 约束

- C1 SKILL.md frontmatter 限开放标准 6 字段：`name` / `description` / `license` / `compatibility` / `metadata` / `allowed-tools`（其余字段在 claude.ai 打包与部分工具中会硬报错）
- C2 SKILL.md 正文 < 500 行；细节下沉 `references/`（渐进式披露）
- C3 文件引用用相对路径（规范层）；`${CLAUDE_SKILL_DIR}` 仅作为 Claude Code 用户的补充写法
- C4 脚本必须非交互（无 TTY 提示）、幂等、`--help` 可用、失败信息可行动
- C5 产物规范（目录树、四产物名、五级标题）以 SKILL.md 的 Output Format 节为单一事实源，`build_html.py` 内的 `ARTIFACT_NAMES` 必须与之一致（由测试钉住）
- C6 skill 不依赖宿主以外的网络服务（研究用的搜索/抓取走宿主自带工具；`git clone` 公开仓库走宿主 shell）

## 5. 目标形态

### 5.1 仓库结构（转型后）

```
LearningFactory/
├── .claude-plugin/
│   ├── plugin.json                    # Claude Code plugin 入口（J1）
│   └── marketplace.json               # 最小 marketplace，保证两步安装确定可跑通（J12）
├── .agents/skills/learning-factory/   # Codex 通用路径（skill 实体，J5）
│   ├── SKILL.md
│   ├── references/
│   │   ├── docs-researcher.md         # ← prompts/docs_researcher.md 改写
│   │   ├── web-researcher.md          # ← prompts/web_researcher.md 改写
│   │   ├── repo-analyzer.md           # ← prompts/repo_analyzer.md 改写（工具段重写，见 §6.3）
│   │   ├── file-writer.md             # ← prompts/file_writer.md 简化（去分块化，见 §6.4）
│   │   └── progressive-learning.md    # ← 现成直搬（68 行五级结构细则）
│   └── scripts/
│       ├── build_html.py              # ← html_builder.py 抽取（PEP 723，见 §6.4 依赖）
│       └── templates/
│           └── learning_page.html     # ← 模板原样直搬（345 行）
├── skills/
│   └── learning-factory -> ../.agents/skills/learning-factory   # symlink（Claude Code plugin 扫描路径）
├── learning_factory/                  # CLI 代码，冻结（J2）
├── tests/                             # 保留 html_builder 相关 ~75 项；CLI 测试随冻结保留不再新增
└── README.md / README.en.md           # 重写安装章节
```

### 5.2 SKILL.md frontmatter（草案）

```yaml
---
name: learning-factory
description: Generate a complete Chinese learning package (5-level learning path, curated resources, runnable code examples, single-file interactive HTML) for any technology topic. Use when the user asks to create a learning plan / study path / 学习计划 for a tool, framework, or technology.
license: MIT
compatibility: macOS or Linux with bash and python3 (3.9+); Windows not supported in v1; uv recommended for script dependencies.
---
```

（description 双语触发词——中英请求都能命中。）

### 5.3 主流程（SKILL.md 正文骨架，英文成稿）

1. **Plan**：确认主题，产出研究分工（docs / repo / web 三路）
2. **Research（并行优先）**：若宿主支持并行子任务，同时派出三路，各携带对应 references 角色卡作为子任务指令；否则按 docs → repo → web 顺序执行（§6.2）
3. **Synthesize**：交叉印证三路结果，去重、排矛盾、标记分歧
4. **Write**：按 Output Format 产出四类产物（file-writer 纪律：简体中文强制、先读后写、一文件一任务）
5. **Build**：调用 `scripts/build_html.py` 聚合单文件 HTML
6. **Verify**：对照 DoD 自检清单（§6.1）逐项核对后向用户汇报

## 6. 缺口解决方案（对应可行性分析缺口①–⑧）

### 6.1 缺口①：编排强制性丢失

CLI 中代码保证的纪律改为**文档纪律 + 完成定义（DoD）自检**：

- SKILL.md 开头置顶「Hard Rules」节：三路研究缺一不可、交叉印证后才可落盘、产物简体中文强制（代码/命令/专有名词保留原文）、一文件一任务
- 流程末尾强制 DoD 清单，宿主逐项自检并**在最终回复中逐项确认**：
  - [ ] 五级标题齐全（概览与动机 / 安装与 Hello World / 核心概念 / 实战模式 / 进阶方向）
  - [ ] 四产物齐全（README.md / resources.md / learning-path.md / code-examples/）
  - [ ] resources.md 中链接均来自本轮研究来源，无编造
  - [ ] HTML 构建成功且报告路径
- 接受质量从「工程确定」降为「提示工程大概率」；DoD 是最后防线

### 6.2 缺口②：子 Agent 跨宿主差异

SKILL.md 用**宿主无关的降级式指令**，不写死任何宿主的工具名：

- 指令措辞（英文成稿）："If your environment supports spawning parallel sub-tasks, dispatch the three research roles concurrently, each with its role card from references/ as the sub-task prompt. Otherwise, complete the three research passes sequentially in order: docs → repo → web."
- Claude Code 实际表现：Task 工具并行派发（实测预期，验收时确认）
- Codex 实际表现：并行 subagent 机制（官方已支持，验收时确认）
- 角色卡独立成文件的意义正在于此：它们直接充当子任务提示词附件
- file_writer 不再是子 Agent：宿主原生写文件无 1500 字符限制，但角色卡保留其纪律（简体中文、先读后写、JSON/代码块转义意识），作为 Write 阶段的行为规范

### 6.3 缺口③：zread 无对等物（repo 研究路径重写）

`repo-analyzer.md` 工具段重写为宿主无关策略：

- 首选：`git clone --depth 1 <repo> <系统临时目录>`，直接用宿主文件工具读源码（比 zread 更强：全仓库可见）
- 备选：宿主网页抓取工具读 GitHub 页面（README、目录浏览）
- 效率规则保留：至多精读 4–5 个关键文件（README / 入口 / 配置 / 示例目录优先）
- 研究完成后临时克隆目录可删除；skill 提示宿主勿把克隆目录留在用户工作区内

### 6.4 缺口④：脚本依赖落地 + file_writer 简化

**build_html.py 依赖策略**（目标：开箱即跑）：

- 脚本头部加 PEP 723 内联依赖声明（`# /// script` → `dependencies = ["markdown", "pygments"]`）
- **Python 3.9+ 语法兼容**（J7）：抽取时消除 PEP 604（`X | None` → `Optional[X]`）等 3.10+ 语法，保证 macOS 自带 3.9.6 可直接跑回退路径
- SKILL.md 指示执行顺序：优先 `uv run scripts/build_html.py <目录>`；uv 缺失时回退 `python3 scripts/build_html.py`；import 失败时提示用户 `pip install markdown pygments` 后重试
- pygments 改为**可选依赖**：try/except 导入，缺失时代码示例降级为无高亮纯文本（功能完整，视觉降级），HTML 构建不因此失败
- markdown 为硬依赖（无可降级方案），缺失时报错信息给出安装命令

**file_writer 简化**：删除 1400/1500 字符分块工作流（宿主 Write 工具无此限制），保留：简体中文强制、先读后写（续作场景）、同文件冲突意识、确定性摘要格式。

### 6.5 缺口⑤：产物规范单一事实源

- SKILL.md 的 Output Format 节定义：目录树 `Learning-Factory/learning-{topic}/`、四产物名、五级中文标题
- `build_html.py` 的 `ARTIFACT_NAMES` / `_STRONG_ARTIFACTS` / `_is_tech_dir` 与之对齐（抽取时改名空间独立，不再 import learning_factory）
- 新增一致性测试：测试同时读 SKILL.md 里列出的产物名与脚本常量，断言一致（防止一处改动漂移）
- 输出根目录默认 `./Learning-Factory/`；用户在对话中指定目录时以用户为准

### 6.6 缺口⑥：测试体系重建

- **单实体迁移**（J9）：`test_html_builder.py`（52）+ `test_cli_build.py`（23）只测新脚本（迁移后修正 import 与被测路径）；包内 `learning_factory/html_builder.py` 冻结保留但不再有直接测试覆盖（代码不动即无回归面），致命 bug 修复时两处同步
- 新增：产物名一致性测试（§6.5）；`claude plugin validate ./`（CI 中若可用）+ `skills-ref validate .agents/skills/learning-factory`；SKILL.md 行数 < 500 的守护测试
- CLI 既有测试（约 160 项）随冻结代码保留，继续跑（防止冻结代码被误改），不新增

### 6.7 缺口⑦：产品形态（J1/J2 待作者确认）

见 §2.2。CLI 冻结的例外：仅修致命 bug 与安全问题的裁量权留给作者本人。

### 6.8 缺口⑧：分发与文档

**安装三态（README 重写后的核心内容）**：

| 宿主 | 安装方式 |
|---|---|
| Claude Code | 主路径：`/plugin marketplace add Shoothedrifter/LearningFactory` → `/plugin install learning-factory@LearningFactory`（J12 的 marketplace.json 保证解析）。免 marketplace 兜底：clone 仓库后把 `.agents/skills/learning-factory/` **复制**到 `~/.claude/skills/`（J11：整仓 clone 到 skills 目录扫不到嵌套 SKILL.md，不可用） |
| Codex CLI | 主路径：`$skill-installer` 从 git URL 装入 `~/.agents/skills/`；或手动复制 `.agents/skills/learning-factory/` 到 `~/.agents/skills/`（J10：不推荐 clone 整仓进用户项目——仓库根的 AGENTS.md 会被当作用户项目指令加载） |
| 其他（通用） | 任何读 `.agents/skills/` 或 `~/.agents/skills/` 的宿主均可直接使用（v1 不承诺测试） |

Codex 前置说明（J6）：零配置指无需配置任何 API Key 与模型参数；宿主首次运行时的沙箱批准（网络访问、临时目录写入）属宿主原生交互，README 予以说明。

**顺手清理（同批提交）**：AGENT.md → AGENTS.md 的未提交重命名正式提交（内容无变化）；CLI 冻结部分不再清理 bash 工具未挂载、bs4 零依赖等历史问题（冻结即封存）。

## 7. 验收标准（v1 完成的定义）

- A1 Claude Code：干净环境安装 skill，新会话说「帮我制定学习 Docker 的学习计划」，产出学习包通过 DoD 全项，HTML 双击可开
- A2 Codex CLI：同场景同标准（顺序降级执行亦可接受，产物质量不降）
- A3 双宿主均未要求用户配置任何 API Key 或模型参数
- A4 CI 全绿：迁移后 pytest + 两类 skill 校验
- A5 README 更新并自测安装步骤可照做

## 8. 工作分解（建议实现顺序）

1. skill 骨架：目录、SKILL.md 成稿、frontmatter、references 五个文件改写
2. 脚本抽取：build_html.py + 模板（PEP 723、pygments 降级、改名空间）
3. 分发接线：plugin.json、symlink、双路径验证
4. 测试迁移 + 新增守护测试 + CI
5. README 重写 + AGENTS.md 提交 + 仓库清理
6. 双宿主冒烟验收（A1/A2）

每步独立可提交；步骤 6 通过前不对外宣传。

## 9. 风险与待验证清单（实现期必须实测）

| # | 风险 | 验证方式 | 缓解 |
|---|---|---|---|
| R1 | symlink 在 Claude Code plugin 安装/打包链路中被破坏或复制为实体 | 本机 `/plugin marketplace add` 全链路实测 | 若失效：改为构建脚本生成双份 + CI 一致性校验（该方案同时是未来支持 Windows 的升级路径，见 J8） |
| R2 | Codex 侧两个未确认面：① skill 激活后脚本路径的解析方式（有无 `${CLAUDE_SKILL_DIR}` 等价物）；② 默认沙箱对 `git clone` 临时目录写入与 `uv run` 首次联网装依赖的放行方式 | Codex 真机跑一次含脚本的 skill，覆盖 §6.3 clone 路径与 §6.4 回退链 | ① SKILL.md 用「skill 安装目录下 scripts/build_html.py」的自然语言定位 + 多种写法并存；② 按 J6 定义的边界，README 说明预期的批准项 |
| R3 | 宿主模型不遵循 DoD/并行指令，产物缩水 | 双宿主各 3 个主题冒烟（Docker/PyTorch/一个冷门主题） | 收紧 SKILL.md 措辞、提高 DoD 位置权重；极端情况接受顺序执行 |
| R4 | uv 普及度不足，回退路径体验差；回退目标 Python 版本过新（macOS 自带 3.9.6） | 无 uv、仅系统 Python 的干净环境实测回退链 | 回退提示清晰化；J7 的 3.9 兼容改写 + pygments 降级已消除主要压力 |
| R5 | description 触发词不足，用户请求未命中 skill | 双宿主各测 5 种问法（中英混合） | description 增补同义词；README 提示可显式点名 skill |
| R6 | 仓库根同时存在 `.claude-plugin/` 与 `.agents/`，某宿主误读对方配置 | 双宿主各自启动扫描确认无副作用 | 预期互不识别、静默忽略；若发现干扰则调整目录布局 |

## 10. 留给实现者的决策

- SKILL.md 英文成稿的具体措辞与 500 行内的篇幅分配
- R1 symlink 失效时的双份生成方案细节（构建脚本 or CI 校验）
- pygments 降级渲染的具体实现（纯 `<pre>` vs 简易着色）
- CI 中 `claude plugin validate` 的可用性兜底（无 CLI 的环境跳过 or 容器安装）
- references 角色卡改写时的删减尺度（保留原提示词结构，删去 OpenAI function-calling 特有表述）
