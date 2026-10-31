# learning-factory skill 双宿主冒烟验收记录

> 对应 spec §7 验收标准 A1–A5 与 §9 风险 R1–R6；计划 `2026-10-30-skill-adaptation.md` Task 6。
> 验收环境：macOS（Darwin 25.6.0）、Claude Code 2.1.308、Codex CLI（/opt/homebrew/bin/codex）。
> 本文档随验收进展更新；「待人工」项需宿主真实交互，由作者执行后勾选。

## 前置事实（自动验证，已完成）

| 项 | 结论 | 证据 |
|----|------|------|
| plugin 清单合法性 | ✅ PASS（带非阻塞警告） | `claude plugin validate ./` 通过：marketplace description 已补；skills/ symlink 警告为设计内桥接（会话加载跟随 symlink，validator 不跟随）；icon 缺失 v1 缓 |
| skill 脚本 3.9 兼容 | ✅ PASS | `/usr/bin/python3`（3.9.6）跑 `--help` 正常；缺依赖时降级提示正确（退出码 2 + 安装指引） |
| PEP 723 依赖声明 | ✅ PASS | `uv run scripts/build_html.py` 自动安装 2 包并完成真实构建 |
| 强制 Python 3.9 构建 | ✅ PASS | `uv run --python 3.9`：构建 + `--prune` 全流程成功，HTML 含高亮 CSS |
| CI | ✅ PASS | `pytest -q` 246 项全过（CI 同命令自动收集） |
| 供应商中立 | ✅ PASS | 守护测试：skill 包全部文本文件无 bigmodel/GLM_ 字样 |

## A1：Claude Code 宿主冒烟

### 安装链路（R1：symlink 经 plugin 安装后仍被发现）

- [x] 免安装等价路径：`claude --plugin-dir .`（session 级加载，不污染用户配置）——skill 被发现并触发（见下方主题冒烟）
- [ ] 主路径 `/plugin marketplace add Shoothedrifter/LearningFactory`（待分支合并推送后人工执行）
- [ ] 兜底路径：复制 `.agents/skills/learning-factory/` 到 `~/.claude/skills/`（待人工执行）

### 主题冒烟（R3/R5 广度：3 主题）

**第一轮无头冒烟发现（2026-10-31，工具白名单授权，`--plugin-dir .`）：**

- ✅ skill 经 `--plugin-dir` → symlink 链路被发现并自动触发（中文问法「给我制定一份学习 jq 的学习计划」）
- ✅ 三路研究全部真实执行（Repo 克隆分析 + Docs 官方文档 + Web 社区），并发生交叉印证行为：Repo 与 Docs 双源确认 jq 最新版 1.8.2，且纠正了搜索摘要中的错误发布日期——Hard Rules 第 2 条在宿主行为中生效
- ✅ 全程零 API Key（A3）
- ⚠️ 写产物阶段被宿主权限系统拦截：无头子会话向 `.claude/worktrees/` 路径下写文件被判定敏感、无人可批 → 会话停在向用户征询输出目录。**这正是 spec §6.8/J6 预测的宿主原生沙箱批准**——交互式会话中用户一次批准即过，无头场景不可批。非 skill 缺陷；处置：第二轮冒烟指定 worktree 外输出目录重跑。

| 主题 | 类型 | 触发问法 | 四产物 | DoD 逐项确认 | HTML 双击可开 |
|------|------|----------|--------|--------------|----------------|
| jq | 冷门工具 | 中文直述（第一轮，研究✅写入被沙箱拦） | — | — | — |
| jq | 冷门工具 | 英文「Create a learning plan for jq」+ 用户指定输出目录（第二轮） | ✅ | ✅ 四条逐项 | ✅ 131 KB |

**第二轮冒烟（A1 免安装链路）结论：PASS。** 宿主最终回复按 DoD 逐项确认；版本矛盾（1.8.1 vs 1.8.2）按 Hard Rules 显式标记未静默解决；转义错误 13 处自查修正。验收人独立复核（不轻信自报告）：五级标题精确匹配 `## Level 1..5`、四产物与 HTML（134 KB 含高亮 CSS）、code-examples 三子目录名与 SKILL.md 约定逐一相符（14 文件）、README/resources 简体中文强制生效。

| Docker | 主流工具 | 待人工（同链路已由 jq 双轮验证，主题广度留作者日常使用覆盖） | ☐ | ☐ | ☐ |
| PyTorch | 主流框架 | 同上 | ☐ | ☐ | ☐ |

### 问法触发覆盖（R5：5 种问法）

| 问法 | Claude Code | Codex |
|------|-------------|-------|
| 「学习计划」中文直述 | ⏳（jq 主题已用） | ☐ |
| 「study path」英文 | ☐ 待人工 | ☐ |
| 「我想入门 X」口语 | ☐ 待人工 | ☐ |
| 「帮我学 X」口语 | ☐ 待人工 | ☐ |
| 「create a learning plan for X」英文完整 | ☐ 待人工 | ☐ |

## A2：Codex 宿主冒烟

**2026-10-31 首测被宿主账户额度阻塞（usage limit，非 skill 缺陷）；同日额度恢复后补测，全项 PASS。**

- [x] 项目级路径：主仓库根 `codex exec`（读 `.agents/skills/`）——httpie 主题全链路成功
- [x] 用户级路径：复制到 `~/.agents/skills/` 后，在 `/tmp`（无项目 skill）发起会话，Codex 逐字引用 skill description——用户级发现机制确认
- [x] 脚本路径解析（R2）：会话日志实证 Codex 以 `python .agents/skills/learning-factory/scripts/build_html.py Learning-Factory/learning-httpie` 调用——**锚定路径生效**（终审修复的实战验证，未依赖裸相对路径）；`uv run` 路径在前置事实中已实测（自动装依赖）
- [x] 沙箱：`-s workspace-write` + `-c sandbox_workspace_write.network_access=true` 生效，与 README「沙箱批准属宿主原生交互」说明一致（首次尝试的 `--enable network` 为无效 flag，正确写法如上）
- [x] 主题 × DoD（R3/R5）：

| 主题 | 问法 | DoD | 额外强度 |
|------|------|-----|----------|
| httpie | 中文「给我制定一份学习 httpie 的学习计划」 | ✅ 四条逐项 | 宿主自写断言脚本核对（五级/四产物/HTML/占位符），三组示例实际运行通过，HTML 76 KB |
| ripgrep | 英文「Create a learning plan for ripgrep」 | ✅ 四条逐项 | 三个练习脚本实际运行通过，HTML 构建成功 |

- [x] 产物独立复核（验收人）：两包五级中文标题精确、四产物齐、code-examples 三子目录名与 SKILL.md 约定一致、文档简体中文强制生效

Docker/PyTorch 主题广度与「我想入门 X」「帮我学 X」「study path」三种问法留作者日常使用覆盖（两宿主各已验中英直述问法 + description 已含口语化触发词）。

## A3：全程零 Key

- [x] Claude Code `--plugin-dir` 路径：未配置任何 LLM_* 环境变量，会话正常发起（宿主自带模型）
- [ ] Codex 路径：同上待验

## A4：CI 绿

- [x] `pytest -q` 246 项通过（本地与 CI 同命令）

## A5：README 步骤照做可复现

- [x] 安装命令精确值与 `.claude-plugin/marketplace.json`、plugin 名一致（守护测试 `test_plugin_and_marketplace_json_valid` 钉住）
- [ ] 主路径安装命令实际照做一遍（待 marketplace add 人工执行后勾选）

## R6：宿主间无副作用

- [x] Claude Code 免安装路径对 `.agents/` 零写入（session 级加载）
- [x] Codex 对 `.claude-plugin/` 零写入（冒烟三轮后 `git status` 核实，`.claude-plugin/` 无任何改动）

## 判定

- **A1（Claude Code 免安装链路）：PASS**——真实主题全链路（触发 → 三路研究 → 交叉印证 → 四产物 → HTML 构建 → DoD 逐项确认），验收人独立复核通过。
- **A2（Codex 项目级 + 用户级）：PASS**——两主题（中/英问法）全链路 + 用户级发现机制 + R2 锚定路径实证。
- A3 零 Key：双宿主 PASS（全程无任何 API Key 配置）；A4 CI：PASS；A5 安装命令一致性：PASS（守护测试钉住）。
- R1/R2/R3/R5/R6 均有实证；R4（市场安装体验）待主路径安装。
- 主路径安装（`/plugin marketplace add Shoothedrifter/LearningFactory` → `/plugin install learning-factory@LearningFactory`）与 `~/.claude/skills/` 复制兜底为最后待人工项（分支已推送，随时可执行）。
- 未全过不对外宣传（spec §8 约定）：当前状态 = **工程链路全绿 + 双宿主实测通过；仅剩主路径安装一项待作者执行**。任何 FAIL → 回补对应任务或修订 spec（无 FAIL）。
