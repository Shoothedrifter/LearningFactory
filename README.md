# 学习工厂（Learning Factory）

多智能体协作研究系统，直接通过 OpenAI 兼容 SDK 调用大模型 API，无需 LangChain / LangGraph 等框架依赖。默认对接智谱 GLM（注册即用），也可切换到其他 OpenAI 兼容供应商（见[配置](#配置)）。

系统由一个**主 Agent**（协调者）和四个**子 Agent**（三路研究专家 + 专职写入引擎）组成，通过 ReAct 循环自动调用工具、分发任务、综合结果。告诉它你想学什么——比如「给我制定一份学习 Docker 的学习计划」——它会并行研究官方文档、代码仓库与社区内容，并在本地生成一套可以直接开始的学习路径。

## 它能做什么

- **一句话请求，生成完整学习包**：五级渐进式学习路径（概述 → 安装上手 → 核心概念 → 实战模式 → 进阶指引）
- **三路并行研究**：官方文档、仓库分析、社区教程同时进行，结果交叉印证
- **产物落盘本地**：导览 README、资源汇总、学习路径主文档、可运行的代码示例，全部写入本地目录
- **多轮对话与任务续作**：中途有文件未完成时，一句「继续完成任务」即可补齐

生成的学习包结构示例：

```
Learning-Factory/learning-docker/
├── README.md            # 概览和使用说明
├── resources.md         # 全部参考链接（按来源分类）
├── learning-path.md     # 五级学习路径主体内容
└── code-examples/
    ├── 01-hello-world/       # 安装与第一批命令
    ├── 02-core-concepts/     # 核心概念配套练习
    └── 03-patterns/          # 实战模式示例
```

## 安装

要求 Python >= 3.11。三种方式任选：

**方式 A：pipx 从 PyPI 直装（推荐，隔离环境、获得 `learning-factory` 命令）**

```bash
pipx install learning-factory
```

**方式 B：pipx 从 GitHub 直装（无需本地仓库副本）**

```bash
pipx install git+https://github.com/Shoothedrifter/LearningFactory.git
```

**方式 C：clone 后 pip 安装（开发场景）**

```bash
git clone https://github.com/Shoothedrifter/LearningFactory.git
cd LearningFactory
pip install -r requirements.txt        # 直跑（含 Web 模式全家桶）
# 或
pip install -e ".[web,dev]"            # 可编辑安装 + Web/开发可选依赖
```

> 依赖版本以 [pyproject.toml](pyproject.toml) 为准（openai / httpx / python-dotenv / mcp / beautifulsoup4；Web 模式另需 fastapi + uvicorn）。

## 配置

在**运行目录**创建 `.env` 文件（可参考 [.env.example](.env.example)），写入你的 API Key（模型供应商如果是智谱 GLM，开箱即用）：

```env
# 以 GLM 供应商获取地址为例：https://bigmodel.cn → API 密钥
LLM_API_KEY="your-api-key-here"
```

也可以不建 `.env`，直接导出环境变量：`export LLM_API_KEY="你的密钥"`。

注意：程序只加载**运行目录**下的 `.env`，不做向上查找——在其他目录运行时请在该目录放置 `.env`。未配置 Key 时启动即打印获取与配置指引并退出，不会等到首次调用才报错。

**换用其他 OpenAI 兼容供应商**：把 `LLM_BASE_URL` 设为该供应商端点，并按其模型列表覆盖 `LLM_MAIN_MODEL` / `LLM_SUB_MODEL` / `LLM_REPO_MODEL`。三个研究工具（网页搜索/抓取、仓库读取）默认走智谱的 MCP 服务 —— 换供应商时把三个 `MCP_*_URL` 一并切换（见下文「研究工具的 MCP 端点」）。

非智谱 GLM 用户的最小配置是 **4 个变量**——只填 `LLM_API_KEY` 不够（默认端点与模型名都是 GLM，其他供应商的 Key 会 401、与智谱模型名冲突）。以 Kimi 与 DeepSeek 为例（模型名以各供应商当前列表为准）：

```env
# Kimi（Moonshot）：https://platform.moonshot.cn → API Key 管理
LLM_API_KEY="<Kimi 的 Key>"
LLM_BASE_URL="https://api.moonshot.cn/v1"
LLM_MAIN_MODEL="<按 Kimi 模型列表填写>"
LLM_SUB_MODEL="<按 Kimi 模型列表填写>"
LLM_REPO_MODEL="<按 Kimi 模型列表填写>"

# DeepSeek：https://platform.deepseek.com → API Keys
LLM_API_KEY="<DeepSeek 的 Key>"
LLM_BASE_URL="https://api.deepseek.com/v1"
LLM_MAIN_MODEL="deepseek-chat"
LLM_SUB_MODEL="deepseek-chat"
LLM_REPO_MODEL="deepseek-chat"
```

**研究工具的 MCP 端点**：三个研究工具默认使用智谱的 MCP 服务，认证与模型 API 共用 `LLM_API_KEY`。换供应商时若其也提供 MCP 服务，把 `MCP_WEB_SEARCH_URL` / `MCP_WEB_READER_URL` / `MCP_ZREAD_URL` 一并切到该供应商端点（Key 继续共用；仅当供应商对 MCP 单独发 Key 时再设 `MCP_API_KEY`）；若不提供，研究工具不可用——主 Agent 调度、Notion 工具、本地文件读写不受影响。

模型切换、MCP 端点覆盖等全部环境变量（写进 `.env` 或直接导出均可）：

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

## 运行

**CLI 模式（终端交互）：**

```bash
learning-factory                          # pipx/pip 安装后的入口命令
# 或（clone 场景未安装时）
python -m learning_factory.agent
```

- 输入 `exit` 退出；输入 `clear` 清空对话历史
- `--resume`：恢复上次会话；指定路径 `--resume ~/.learning_factory/sessions/<文件>.jsonl`
- `--output-dir <目录>`：产物输出根目录（默认 `Learning-Factory/`）
- 过程实时可见：子 Agent 启动/完成（`▶`/`✔`/`✖`）与工具调用逐行打印，最终答案整段输出

**Web 模式（浏览器访问）：**

```bash
python -m learning_factory.server
```

浏览器打开 `http://localhost:8000`：实时过程面板（工具调用、子 Agent 调度）、Markdown 渲染的最终答案、会话管理。

## 会话持久化（CLI）

CLI 模式的对话历史逐轮落盘到家目录 `~/.learning_factory/sessions/`（JSONL 格式，立即写盘不留缓冲），进程崩溃也保留已写轮次；pipx 场景在任意目录启动都写到同处。

- `--resume`：恢复最近一次会话；`--resume <文件路径>` 恢复指定会话
- 恢复时自动裁掉尾部连续的未回应消息；找不到可恢复会话时开启新会话
- 输入 `clear` 清空历史时会开启新会话文件，旧会话文件保留

## 更多文档

架构设计（Agent 协作 / ReAct 循环）、工具系统与分配、MCP 集成、Skill 系统、SSE 事件协议、环境变量全表、与原版 claude_agent_sdk 的对应关系——全部见 **[AGENT.md](AGENT.md)**。

## 开发与测试

```bash
pip install -r requirements-dev.txt
pytest    # 145 项，全 mock 无需真实 API Key
```

## 注意事项

- Bash 工具会在本机执行命令，请确保在可信环境中运行
- `.env` 文件包含 API 密钥，不应提交到版本控制
- `Learning-Factory/` 下的 `learning-pytorch/` 等目录是系统生成的学习产物（已在 `.gitignore` 中，不入库）

## 许可证

[MIT](LICENSE)
