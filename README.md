# 多智能体系统（GLM-4 重构版）

基于智谱 AI GLM-4 的多智能体协作研究系统，直接通过 OpenAI SDK 调用 GLM-4 API，无需 LangChain / LangGraph 等框架依赖。

系统包含一个**主 Agent**（协调者）和三个**子 Agent**（专家），通过 ReAct 循环自动调用工具、分发任务、综合结果。

## 项目结构

```
.
├── agent.py                    # 主入口：CLI 对话循环 + 主 Agent 定义（普通 + 流式版本）
├── server.py                   # FastAPI Web 服务（SSE 流式推送 + 会话管理）
│
├── agents/
│   ├── base.py                 # 核心 Agent Loop：ReAct 模式（普通 + 流式版本）
│   └── subagents.py            # 三个子 Agent 定义及调度表（普通 + 流式版本）
│
├── tools/
│   ├── __init__.py             # 工具注册表：函数名 → 实现函数的映射
│   ├── mcp_client.py           # MCP 连接管理器：通用 MCP 工具调用函数
│   ├── web.py                  # 网页搜索 + 网页抓取（通过 MCP 服务器）
│   ├── bash.py                 # Shell 命令执行（asyncio.subprocess）
│   ├── notion.py               # Notion REST API（搜索页面 + 追加内容块）
│   ├── repo.py                 # GitHub 仓库分析（目录结构/文件读取/文档搜索）
│   └── filesystem.py           # 本地文件操作（写文件 + 列目录）
│
├── prompts/                    # 系统提示词（Markdown 格式）
│   ├── main_agent.md           #   主 Agent：研究协调者
│   ├── docs_researcher.md      #   文档研究员
│   ├── repo_analyzer.md        #   仓库分析员
│   └── web_researcher.md       #   网络研究员
│
├── static/
│   └── index.html              # Web 聊天前端（SSE 消费 + Markdown 渲染 + 过程可视化）
│
├── .claude/
│   └── skills/
│       └── learning-a-tool/    # Skill 定义：编程工具学习路径生成
│           ├── SKILL.md        #   工作流定义（研究 → 结构 → 输出）
│           └── references/
│               └── progressive-learning.md  # 渐进式学习框架（5 个层级）
│
├── requirements.txt            # Python 依赖
└── .env                        # 环境变量（API 密钥）
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
           │ dispatch_to_subagent
           ├──────────┬──────────┬──────────┐
           ▼          ▼          ▼          ▼
  ┌────────────┐ ┌──────────┐ ┌──────────┐
  │docs_researcher│ │repo_analyzer│ │web_researcher│
  │ glm-5-turbo │ │glm-5│ │glm-5-turbo│
  │ Search+Fetch│ │Repo工具  │ │Search+Fetch│
  └────────────┘ └──────────┘ └──────────┘
        │              │             │
        └──────┬───────┘─────────────┘
               ▼
         汇总 → 主 Agent 合成最终输出
```

> **并行执行**：主 Agent 同一轮返回的多个工具调用（包括多个 `dispatch_to_subagent`）通过
> `asyncio.gather` 并发执行。Skill 工作流要求的"同时分派 3 个子 Agent"是真正的并行——
> 三个子 Agent 的研究同时进行，总耗时约等于最慢的那个，而非三者之和。
> 流式版本通过共享事件队列实时转发并行任务的过程事件（事件协议不变，前端无需改动）。

### 核心 Agent Loop（ReAct 模式）

`agents/base.py` 实现了标准的 ReAct (Reasoning + Acting) 循环：

1. **调用模型** — 将 system prompt + 对话历史 + 工具定义发送给 GLM-4
2. **判断响应** — 模型返回工具调用则执行工具，否则返回最终文本答案
3. **执行工具** — 从 `TOOL_REGISTRY` 查找对应函数，异步执行并将结果追加到历史
4. **循环迭代** — 重复步骤 1-3，直到模型不再调用工具或达到最大轮次（默认 10 轮）
5. **兜底总结** — 达到最大轮次时，强制做一次无工具的总结调用

### 工具系统

所有工具通过 `tools/__init__.py` 中的 `TOOL_REGISTRY` 字典统一注册，Agent Loop 通过函数名查找并调用。

| 工具 | 实现文件 | 说明 |
|------|----------|------|
| `web_search` | `tools/web.py` | 网页搜索，通过 MCP `web_search_prime` 服务器 |
| `web_fetch` | `tools/web.py` | 抓取网页内容（Markdown 格式），通过 MCP `web_reader` 服务器 |
| `bash` | `tools/bash.py` | 执行本地 shell 命令（30s 超时，5000 字符截断） |
| `notion_search` | `tools/notion.py` | 搜索 Notion 页面/数据库 |
| `notion_append_block` | `tools/notion.py` | 向 Notion 页面追加段落内容 |
| `repo_structure` | `tools/repo.py` | 获取 GitHub 仓库目录结构 |
| `repo_read_file` | `tools/repo.py` | 读取 GitHub 仓库文件内容 |
| `repo_search` | `tools/repo.py` | 搜索仓库文档/issues/commits |
| `write_file` | `tools/filesystem.py` | 写入本地文件（含路径穿越保护） |
| `list_directory` | `tools/filesystem.py` | 列出目录内容 |
| `append_file` | `tools/filesystem.py` | 分块追加写入长文档（每块 ≤1500 字符） |
| `load_skill` | `tools/skills.py` | 按需加载技能完整工作流与参考文件 |

### 工具分配

| Agent | 可用工具 |
|-------|----------|
| 主 Agent | `dispatch_to_subagent`, `notion_search`, `notion_append_block`, `write_file`, `list_directory`, `web_search`, `web_fetch` |
| docs_researcher | `web_search`, `web_fetch` |
| repo_analyzer | `web_search`, `web_fetch`, `repo_structure`, `repo_read_file`, `repo_search` |
| web_researcher | `web_search`, `web_fetch` |

### MCP 集成

系统通过 `tools/mcp_client.py` 统一管理 MCP 服务器连接，使用 `mcp` SDK 的 `streamable_http_client` 连接 HTTP 类型的 MCP 服务器：

| MCP 服务器 | 端点 | 用途 |
|------------|------|------|
| `web_search_prime` | `open.bigmodel.cn/api/mcp/web_search_prime/mcp` | 网页搜索 |
| `web_reader` | `open.bigmodel.cn/api/mcp/web_reader/mcp` | 网页内容抓取 |
| `zread` | `open.bigmodel.cn/api/mcp/zread/mcp` | GitHub 仓库读取 |

MCP 调用使用 `GLM_API_KEY` 进行认证，无需额外配置。

### Skill 系统

`.claude/skills/` 目录支持技能，采用**渐进披露**机制：系统提示词只注入技能清单（frontmatter 的 name + description，几百字符），主 Agent 判断用户请求匹配某技能后，通过 `load_skill` 工具按需加载 SKILL.md 完整工作流，`references/` 参考文件再用 `reference` 参数按需读取——技能全文不再常驻每轮请求的上下文。

注：技能全文不常驻对话——多轮会话中每轮需要时可再次调用 `load_skill` 按需加载。

当前内置 `learning-a-tool` Skill：

**触发条件**：用户请求学习某个编程工具/库/框架时自动匹配。

**工作流**：
1. **研究阶段** — 同时分派全部 3 个子 Agent 收集信息
   - `docs_researcher` → 官方文档（版本、核心概念、API、示例）
   - `repo_analyzer` → 仓库分析（架构、README、examples 目录）
   - `web_researcher` → 社区内容（教程、视频、讨论、常见坑）
2. **结构化阶段** — 按 5 级渐进式学习框架组织内容
3. **输出阶段** — 使用 `write_file` 工具在本地生成 `Learning-Factory/learning-{tool-name}/` 目录

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

普通版本用 `print()` 输出到终端，流式版本用 `yield` 推送 SSE 事件。

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

依赖列表：

| 包 | 版本 | 用途 |
|----|------|------|
| `openai` | >=1.30.0 | GLM-4 API（兼容 OpenAI SDK） |
| `httpx` | >=0.27.0 | 异步 HTTP（Notion API） |
| `python-dotenv` | >=1.0.0 | 环境变量加载 |
| `mcp` | >=1.0.0 | MCP SDK（连接 MCP 服务器） |
| `beautifulsoup4` | >=4.12.0 | HTML 解析 |
| `fastapi` | >=0.110.0 | Web 框架 |
| `uvicorn` | >=0.27.0 | ASGI 服务器 |

### 2. 配置环境变量

创建 `.env` 文件（可参考以下模板）：

```env
# 智谱 AI API Key（必需）
# 获取地址：https://bigmodel.cn → API 密钥
GLM_API_KEY="your-api-key-here"

# Notion Integration Token（可选，仅在使用 Notion 工具时需要）
# 获取地址：https://www.notion.so/my-integrations
NOTION_TOKEN="your-notion-token-here"
```

> **注意**：网页搜索、网页抓取、GitHub 仓库分析工具通过智谱 MCP 服务器提供，使用 `GLM_API_KEY` 认证，无需额外配置 Serper 等第三方 API Key。

### 3. 运行

**CLI 模式（终端交互）：**

```bash
python agent.py
```

- 输入 `exit` 退出
- 输入 `clear` 清空对话历史
- 支持多轮对话，对话历史保存在内存中

**Web 模式（浏览器访问）：**

```bash
python server.py
```

浏览器打开 `http://localhost:8000`，聊天界面功能：
- 实时展示 Agent 中间过程（工具调用、子 Agent 调度）
- 折叠式过程面板，可展开查看详情
- Markdown 格式渲染最终答案
- `New Chat` 按钮清空会话

### SSE 事件类型

Web 模式下，`POST /chat` 端点以 `text/event-stream` 推送以下事件：

| 事件类型 | 字段 | 说明 |
|----------|------|------|
| `status` | `agent`, `message` | 状态更新（开始处理、轮次信息） |
| `tool_call` | `agent`, `tool`, `args`, `result`, `status` | 工具调用详情 |
| `subagent` | `subagent`, `status`, `task` | 子 Agent 开始/完成 |
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

## 模型配置

| Agent | 模型 | 配置位置 | 说明 |
|-------|------|----------|------|
| 主 Agent | `glm-5` | `agent.py` → `MAIN_AGENT_MODEL` | 需要复杂推理和协调能力 |
| docs_researcher | `glm-5-turbo` | `agents/subagents.py` → `_SUB_AGENT_MODEL` | 搜索任务，速度快成本低 |
| repo_analyzer | `glm-5` | `agents/subagents.py` → 硬编码 | 仓库分析需要可靠调用多个工具（15 轮上限） |
| web_researcher | `glm-5-turbo` | `agents/subagents.py` → `_SUB_AGENT_MODEL` | 搜索任务，速度快成本低 |

API 端点：`https://open.bigmodel.cn/api/paas/v4/`（兼容 OpenAI SDK）

## 与原版的对应关系

| 原版（claude_agent_sdk） | 重构版 |
|---|---|
| `ClaudeSDKClient` | `agent.py` 中的 `main()` 对话循环 |
| `ClaudeAgentOptions` | `MAIN_AGENT_TOOLS` + `run_main_agent()` |
| `AgentDefinition` | `agents/subagents.py` 中各 `run_*` 函数 |
| `model="sonnet"` | `glm-5` |
| `model="haiku"` | `glm-5-turbo` |
| MCP notion 服务器 | `tools/notion.py` 直接调用 Notion REST API |
| 内置 `WebSearch` 工具 | `tools/web.py` → MCP `web_search_prime` |
| 内置 `WebFetch` 工具 | `tools/web.py` → MCP `web_reader` |
| 内置 `Bash` 工具 | `tools/bash.py` → asyncio.subprocess |
| — | `tools/repo.py` → MCP `zread`（新增） |
| — | `tools/filesystem.py`（新增，Skill 输出用） |
| — | `.claude/skills/` Skill 系统（新增） |

## 开发与测试

```bash
pip install -r requirements-dev.txt
pytest
```

测试覆盖：同轮多工具调用的并行执行（并发峰值断言）、OpenAI 消息协议完整性
（tool_call_id 顺序回填）、单个工具失败的隔离性（错误成为该工具的结果，不影响其他工具）。

## 注意事项

- `prompts/` 目录下的 4 个 `.md` 文件直接复用原项目提示词，无需修改
- Notion 集成从 MCP 改为直接 REST API，功能等价（search + append block）
- Bash 工具会在本机执行命令，请确保在可信环境中运行
- Web 模式的会话存储在内存中，不支持持久化
- `learning-pytorch/` 等目录是 Skill 系统生成的输出示例，非项目核心代码
- `.env` 文件包含 API 密钥，不应提交到版本控制
