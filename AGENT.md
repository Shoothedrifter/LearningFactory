# 学习工厂（Learning Factory）——架构与开发文档

本文面向贡献者与维护者，记录系统的完整架构设计、工具系统、协议与配置真相。用户侧的安装与使用说明见 [README.md](README.md)。

## 项目结构

```
.
├── learning_factory/                # 可安装包（代码 + 提示词 + 技能 + 静态资源随包分发）
│   ├── agent.py                # 主入口：CLI 对话循环 + 主 Agent 定义（普通 + 流式版本）
│   ├── server.py               # FastAPI Web 服务（SSE 流式推送 + 会话管理）
│   │
│   ├── agents/
│   │   ├── base.py             # 核心 Agent Loop：ReAct 模式（普通 + 流式版本）
│   │   └── subagents.py        # 四个子 Agent 定义及调度表（普通 + 流式版本）
│   │
│   ├── tools/
│   │   ├── __init__.py         # 工具注册表：函数名 → 实现函数的映射
│   │   ├── mcp_client.py       # MCP 连接管理器：通用 MCP 工具调用函数
│   │   ├── web.py              # 网页搜索 + 网页抓取（通过 MCP 服务器）
│   │   ├── bash.py             # Shell 命令执行（asyncio.subprocess）
│   │   ├── notion.py           # Notion REST API（搜索页面 + 追加内容块）
│   │   ├── repo.py             # GitHub 仓库分析（目录结构/文件读取/文档搜索）
│   │   ├── filesystem.py       # 本地文件操作（分块写入/追加 + 分页读取 + 列目录）
│   │   └── skills.py           # 技能渐进披露加载 + 输出根目录配置
│   │
│   ├── prompts/                # 系统提示词（Markdown 格式，包内路径、任意 cwd 可读）
│   │   ├── main_agent.md       #   主 Agent：研究协调者
│   │   ├── docs_researcher.md  #   文档研究员
│   │   ├── repo_analyzer.md    #   仓库分析员
│   │   ├── web_researcher.md   #   网络研究员
│   │   └── file_writer.md      #   写入引擎（分块工作流 + 写后验证）
│   │
│   ├── static/
│   │   └── index.html          # Web 聊天前端（SSE 消费 + Markdown 渲染 + 过程可视化）
│   │
│   └── skills/
│       └── learning-a-tool/    # Skill 定义：编程工具学习路径生成
│           ├── SKILL.md        #   工作流定义（研究 → 结构 → 输出）
│           └── references/
│               └── progressive-learning.md  # 渐进式学习框架（5 个层级）
│
├── tests/                      # pytest 测试（145 项，全 mock 无需真实 API Key）
├── pyproject.toml              # 打包与依赖真相（入口点 learning-factory、requires-python>=3.11）
├── requirements.txt            # git clone 直跑场景的依赖清单（版本以 pyproject.toml 为准）
└── .env                        # 环境变量（API 密钥，从 .env.example 复制）
```

## 架构设计

### Agent 协作模式

```
用户请求
    │
    ▼
┌─────────────────────────────────┐
│  主 Agent (glm-5)          │  分析请求、分派任务、综合结果
│  工具: dispatch / Notion / 文件  │
└──────────┬──────────────────────┘
           │ dispatch_to_subagent（研究阶段三路并行）
           ├──────────┬──────────┬──────────┐
           ▼          ▼          ▼          ▼（输出阶段）
  ┌────────────┐ ┌──────────┐ ┌──────────┐ ┌────────────┐
  │docs_researcher│ │repo_analyzer│ │web_researcher│ │file_writer │
  │ glm-5-turbo │ │glm-5│ │glm-5-turbo│ │glm-5-turbo │
  │ Search+Fetch│ │Repo工具  │ │Search+Fetch│ │ 分块写入    │
  └────────────┘ └──────────┘ └──────────┘ └────────────┘
        │              │             │
        └──────┬───────┴─────────────┘
               ▼
         汇总 → 主 Agent 合成最终输出 / dispatch file_writer 落盘
```

> **并行执行**：主 Agent 同一轮返回的多个工具调用（包括多个 `dispatch_to_subagent`）通过
> `asyncio.gather` 并发执行。Skill 工作流的"同时分派 3 个子 Agent"研究阶段为并发执行，
> 经信号量节流为同轮最多 2 个同时运行（三路研究呈 2+1 波），总耗时不等于三者之和。
> 流式版本通过共享事件队列实时转发并行任务的过程事件（事件协议不变，前端无需改动）。
> **限流防护（双层指数退避）**：dispatch 并发经信号量节流（同轮最多 2 个子 Agent 同时运行，重试等待期间也占槽）。
> 子 Agent 每轮的 create 调用撞 429 时在原地按 2/4/8 秒指数退避重试（`base.py` `_create_with_backoff`，
> 已执行的工具轮次零损失）；穿透后才到 dispatch 层按 2/4 秒退避整跑重试。两层叠加后 429 需连续穿透
> 5 次退避（约 30 秒窗口）才会作为失败回填主 Agent，不再依赖主 Agent 消耗轮次补派。
> 同轮指向同一文件的多个 file_writer 任务会被确定性防线拦截（只放行首个，其余推迟到下一轮），
> 防止并发写同一文件导致内容静默颠倒。

### 核心 Agent Loop（ReAct 模式）

`learning_factory/agents/base.py` 实现了标准的 ReAct (Reasoning + Acting) 循环：

1. **调用模型** — 将 system prompt + 对话历史 + 工具定义发送给 GLM
2. **判断响应** — 模型返回工具调用则执行工具，否则返回最终文本答案
3. **执行工具** — 从 `TOOL_REGISTRY` 查找对应函数，异步执行并将结果追加到历史
4. **循环迭代** — 重复步骤 1-3，直到模型不再调用工具或达到最大轮次（主 Agent 12 轮；子 Agent 按角色 10/15/40 轮）
5. **兜底总结** — 达到最大轮次时，强制做一次无工具的总结调用

### 工具系统

所有工具通过 `learning_factory/tools/__init__.py` 中的 `TOOL_REGISTRY` 字典统一注册，Agent Loop 通过函数名查找并调用。

| 工具 | 实现文件 | 说明 |
|------|----------|------|
| `web_search` | `learning_factory/tools/web.py` | 网页搜索，通过 MCP `web_search_prime` 服务器 |
| `web_fetch` | `learning_factory/tools/web.py` | 抓取网页内容（Markdown 格式），通过 MCP `web_reader` 服务器 |
| `bash` | `learning_factory/tools/bash.py` | 执行本地 shell 命令（30s 超时，5000 字符截断） |
| `notion_search` | `learning_factory/tools/notion.py` | 搜索 Notion 页面/数据库 |
| `notion_append_block` | `learning_factory/tools/notion.py` | 向 Notion 页面追加段落内容 |
| `repo_structure` | `learning_factory/tools/repo.py` | 获取 GitHub 仓库目录结构 |
| `repo_read_file` | `learning_factory/tools/repo.py` | 读取 GitHub 仓库文件内容 |
| `repo_search` | `learning_factory/tools/repo.py` | 搜索仓库文档/issues/commits |
| `write_file` | `learning_factory/tools/filesystem.py` | 写入本地文件（file_writer 子 Agent 专用；单次 ≤1500 字符、超限拒绝并引导分块；覆盖非空文件需 `overwrite=true`；含路径穿越保护） |
| `read_file` | `learning_factory/tools/filesystem.py` | 分页读取本地文件（offset/limit 续读） |
| `list_directory` | `learning_factory/tools/filesystem.py` | 列出目录内容 |
| `append_file` | `learning_factory/tools/filesystem.py` | 分块追加写入长文档（file_writer 子 Agent 专用，每块 ≤1500 字符） |
| `load_skill` | `learning_factory/tools/skills.py` | 按需加载技能完整工作流与参考文件 |

### 工具分配

| Agent | 可用工具 |
|-------|----------|
| 主 Agent | `dispatch_to_subagent`, `load_skill`, `notion_search`, `notion_append_block`, `read_file`, `list_directory`, `web_search`, `web_fetch` |
| docs_researcher | `web_search`, `web_fetch` |
| repo_analyzer | `web_search`, `web_fetch`, `repo_structure`, `repo_read_file`, `repo_search` |
| web_researcher | `web_search`, `web_fetch` |
| file_writer | `write_file`, `append_file`, `read_file`, `list_directory` |

### MCP 集成

系统通过 `learning_factory/tools/mcp_client.py` 统一管理 MCP 服务器连接，使用 `mcp` SDK 的 `streamable_http_client` 连接 HTTP 类型的 MCP 服务器：

| MCP 服务器 | 端点 | 用途 |
|------------|------|------|
| `web_search_prime` | `open.bigmodel.cn/api/mcp/web_search_prime/mcp` | 网页搜索 |
| `web_reader` | `open.bigmodel.cn/api/mcp/web_reader/mcp` | 网页内容抓取 |
| `zread` | `open.bigmodel.cn/api/mcp/zread/mcp` | GitHub 仓库读取 |

MCP 调用使用 `MCP_API_KEY` 认证，不设则回落 `LLM_API_KEY` 共用——模型与研究工具默认来自同一供应商，一套 Key 即可（供应商对 MCP 单独发 Key 时才需并设）。上表为默认端点（智谱官方），可通过 `MCP_WEB_SEARCH_URL` / `MCP_WEB_READER_URL` / `MCP_ZREAD_URL` 覆盖（见[环境变量配置表](#环境变量配置表)）。非智谱用户注意：模型侧需同时覆盖 `LLM_BASE_URL` 与三个模型名（最小配置 4 变量，README 配置节有 Kimi/DeepSeek 完整示例）；研究工具端点随供应商一并切换，供应商不提供 MCP 服务时研究工具不可用（主 Agent 调度、Notion、本地文件读写不受影响）。

### Skill 系统

`learning_factory/skills/` 目录支持技能，采用**渐进披露**机制：系统提示词只注入技能清单（frontmatter 的 name + description，几百字符），主 Agent 判断用户请求匹配某技能后，通过 `load_skill` 工具按需加载 SKILL.md 完整工作流，`references/` 参考文件再用 `reference` 参数按需读取——技能全文不再常驻每轮请求的上下文。

注：技能全文不常驻对话——多轮会话中每轮需要时可再次调用 `load_skill` 按需加载。

当前内置 `learning-a-tool` Skill：

**触发条件**：用户请求学习某个编程工具/库/框架时自动匹配。

**工作流**：
1. **研究阶段** — 同时分派全部 3 个子 Agent 收集信息
   - `docs_researcher` → 官方文档（版本、核心概念、API、示例）
   - `repo_analyzer` → 仓库分析（架构、README、examples 目录）
   - `web_researcher` → 社区内容（教程、视频、讨论、常见坑）
2. **结构化阶段** — 按 5 级渐进式学习框架组织内容
3. **输出阶段** — 主 Agent 自身无写入工具，为每个输出文件 dispatch `file_writer` 子 Agent（一轮一文件），在 `Learning-Factory/learning-{tool-name}/` 目录下生成本地文件

**输出结构**：
```
Learning-Factory/learning-{tool-name}/
├── README.md           # 概览和使用说明
├── resources.md        # 所有链接（按来源分类）
├── learning-path.md    # 五级学习路径主体内容
└── code-examples/
    ├── 01-hello-world/
    ├── 02-core-concepts/
    └── 03-patterns/
```

## 两种运行模式

每个 Agent 都有普通版本和流式版本两套函数：

| 普通版本（CLI 用） | 流式版本（Web SSE 用） |
|---|---|
| `run_agent()` | `run_agent_stream()` |
| `run_main_agent()` | `run_main_agent_stream()` |
| `run_docs_researcher()` | `run_docs_researcher_stream()` |
| `run_repo_analyzer()` | `run_repo_analyzer_stream()` |
| `run_web_researcher()` | `run_web_researcher_stream()` |
| `run_file_writer()` | `run_file_writer_stream()` |

普通版本用 `print()` 输出到终端，流式版本用 `yield` 推送 SSE 事件。

CLI 模式同样走流式版本（`main()` 调用 `run_main_agent_stream`），过程事件经 `render_event` 纯函数渲染为终端行：

| 事件 | 渲染 |
|------|------|
| subagent start | `▶ [子Agent名] 任务摘要`（超 50 字符中段省略、保留尾部文件名） |
| subagent done（ok/缺省） | `✔ [子Agent名] 完成` |
| subagent done（ok=false） | `✖ [子Agent名] 失败` |
| tool_call | `· 工具名(...)` |
| 429 重试 | `→ [重试] 子Agent名 撞到速率限制，N 秒后重试...`（N 为指数退避序列值） |
| answer | 整段输出 |

## Web 模式协议

> **状态：暂不开放（follow up）**——`server.py` 待修复，当前以 CLI 为准。本节保留协议现状供修复参照。

### SSE 事件类型

Web 模式下，`POST /chat` 端点以 `text/event-stream` 推送以下事件：

| 事件类型 | 字段 | 说明 |
|----------|------|------|
| `status` | `agent`, `message` | 状态更新（开始处理、轮次信息） |
| `tool_call` | `agent`, `tool`, `args`, `result`, `status` | 工具调用详情 |
| `subagent` | `subagent`, `status`, `task`, `ok` | 子 Agent 开始/完成（`ok` 为 done 时的成败标记，缺省为成功） |
| `answer` | `agent`, `content` | 最终答案 |
| `error` | `message` | 错误信息 |

### Web API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 聊天前端页面 |
| `/chat` | POST | SSE 流式聊天，请求体 `{"message": "...", "session_id": "..."}` |
| `/session` | POST | 创建新会话 |
| `/session/{id}` | DELETE | 删除会话 |

会话存储在内存中，服务器重启后清空。

## 环境变量配置表

模型供应商端点与模型配置集中在 `learning_factory/config.py` 读取，环境变量可覆盖；均可写进运行目录的 `.env`（参考 `.env.example`）或直接导出。

| 环境变量 | 必需 | 默认值 | 用途 |
|----------|------|--------|------|
| `LLM_API_KEY` | 是 | —（未配置则启动即退出） | 模型供应商 API 密钥 |
| `LLM_BASE_URL` | 否 | `https://open.bigmodel.cn/api/paas/v4/` | 模型供应商 OpenAI 兼容端点（自建代理/兼容网关时覆盖） |
| `LLM_MAIN_MODEL` | 否 | `glm-5` | 主 Agent 模型 |
| `LLM_SUB_MODEL` | 否 | `glm-5-turbo` | 子 Agent 通用模型（docs_researcher / web_researcher / file_writer） |
| `LLM_REPO_MODEL` | 否 | `glm-5` | repo_analyzer 专用模型 |
| `MCP_API_KEY` | 否 | 回落 `LLM_API_KEY` | MCP 研究工具独立认证（供应商对 MCP 单独发 Key 时设） |
| `MCP_WEB_SEARCH_URL` | 否 | `https://open.bigmodel.cn/api/mcp/web_search_prime/mcp` | MCP 网页搜索端点 |
| `MCP_WEB_READER_URL` | 否 | `https://open.bigmodel.cn/api/mcp/web_reader/mcp` | MCP 网页抓取端点 |
| `MCP_ZREAD_URL` | 否 | `https://open.bigmodel.cn/api/mcp/zread/mcp` | MCP GitHub 仓库读取端点 |

各 Agent 使用的模型（默认值，均可用上表环境变量调整）：

| Agent | 模型 | 覆盖变量 | 说明 |
|-------|------|----------|------|
| 主 Agent | `glm-5` | `LLM_MAIN_MODEL` | 需要复杂推理和协调能力 |
| docs_researcher | `glm-5-turbo` | `LLM_SUB_MODEL` | 搜索任务，速度快成本低 |
| repo_analyzer | `glm-5` | `LLM_REPO_MODEL` | 仓库分析需要可靠调用多个工具（15 轮上限） |
| web_researcher | `glm-5-turbo` | `LLM_SUB_MODEL` | 搜索任务，速度快成本低 |
| file_writer | `glm-5-turbo` | `LLM_SUB_MODEL` | 分块写入任务（40 轮预算），速度快成本低 |

## 会话持久化（CLI）

CLI 模式的对话历史逐轮追加落盘到家目录 `~/.learning_factory/sessions/`（JSONL 格式，一行一条消息，立即写盘不留缓冲），进程崩溃也保留已写轮次。家目录固定，不随运行目录变化（pipx 场景在任意 cwd 启动都写到同处）。

- `--resume`：恢复最近一次会话（按文件名时间序取最新）
- `--resume <文件路径>`：恢复指定的 `.jsonl` 会话文件
- 恢复时自动裁掉尾部连续的未回应消息；找不到可恢复会话时开启新会话
- 输入 `clear` 清空对话历史时会开启新会话文件，旧会话文件保留

## 与原版的对应关系

| 原版（claude_agent_sdk） | 重构版 |
|---|---|
| `ClaudeSDKClient` | `learning_factory/agent.py` 中的 `main()` 对话循环 |
| `ClaudeAgentOptions` | `MAIN_AGENT_TOOLS` + `run_main_agent()` |
| `AgentDefinition` | `learning_factory/agents/subagents.py` 中各 `run_*` 函数 |
| `model="sonnet"` | `glm-5` |
| `model="haiku"` | `glm-5-turbo` |
| MCP notion 服务器 | `learning_factory/tools/notion.py` 直接调用 Notion REST API |
| 内置 `WebSearch` 工具 | `learning_factory/tools/web.py` → MCP `web_search_prime` |
| 内置 `WebFetch` 工具 | `learning_factory/tools/web.py` → MCP `web_reader` |
| 内置 `Bash` 工具 | `learning_factory/tools/bash.py` → asyncio.subprocess |
| — | `learning_factory/tools/repo.py` → MCP `zread`（新增） |
| — | `learning_factory/tools/filesystem.py`（新增，Skill 输出用） |
| — | `learning_factory/skills/` Skill 系统（新增） |

## 开发与测试

```bash
pip install -r requirements-dev.txt
pytest
```

测试覆盖（145 项）：同轮多工具并行执行与消息协议完整性（tool_call_id 顺序回填、单工具失败隔离）、
分块写入硬限制（1500 字符）与覆盖防线、同轮同文件写/dispatch 双防线（路径两级启发式提取）、
dispatch 429 退避重试与并发节流（信号量）、Skill 渐进披露三层加载、模型配置钉住、
供应商中立钉住（`test_no_glm_names.py`）与 MCP Key 回落（`test_mcp_key_fallback.py`）等。

## 注意事项

- `learning_factory/prompts/` 目录下的 5 个 `.md` 文件中，4 个研究/协调提示词直接复用原项目，`file_writer.md` 为本项目新增
- Notion 集成从 MCP 改为直接 REST API，功能等价（search + append block）
- Bash 工具会在本机执行命令，请确保在可信环境中运行
- `Learning-Factory/` 下的 `learning-pytorch/` 等目录是 Skill 系统生成的输出产物（在 `.gitignore` 中，不入库）
- `.env` 文件包含 API 密钥，不应提交到版本控制
