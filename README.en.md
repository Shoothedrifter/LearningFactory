# Learning Factory

**English** | [中文](README.md)

> Still lost deciding where to start with a new technology? Still spending entire evenings hunting for tutorials, vetting resources, and piecing together a learning path?
>
> Hand all of that to **Learning Factory**: name what you want to learn in one sentence, and it produces a ready-to-start learning pack on your local machine — a five-level learning path, curated references, and runnable code examples.

A multi-agent collaborative research system that calls LLM APIs directly through the OpenAI-compatible SDK, with no LangChain / LangGraph or other framework dependencies. It targets Zhipu GLM out of the box (works right after sign-up) and can be switched to any other OpenAI-compatible provider (see [Configuration](#configuration)).

The system consists of one **main agent** (the coordinator) and four **sub-agents** (three research specialists + a dedicated writing engine), orchestrating tool calls, task dispatch, and result synthesis automatically through a ReAct loop. Tell it what you want to learn — say, "Make me a learning plan for Docker" — and it researches official docs, the code repository, and community content in parallel, then generates a ready-to-start learning path on your local machine.

## What It Does

- **One-sentence request, complete learning pack**: a five-level progressive learning path (overview → installation & first steps → core concepts → practical patterns → advanced guidance)
- **Three parallel research tracks**: official docs, repository analysis, and community tutorials run concurrently, with cross-validated results
- **Artifacts written to local disk**: an overview README, a resource roundup, the main learning-path document, and runnable code examples, all written into a local directory
- **Multi-turn conversation & task continuation**: when files are left unfinished, a single "continue the task" completes them

Example structure of a generated learning pack:

```
Learning-Factory/learning-docker/
├── README.md            # Overview and usage notes
├── resources.md         # All reference links (grouped by source)
├── learning-path.md     # The five-level learning path
└── code-examples/
    ├── 01-hello-world/       # Installation and first commands
    ├── 02-core-concepts/     # Exercises for core concepts
    └── 03-patterns/          # Practical pattern examples
```

## Installation

Requires Python >= 3.11. Pick one of three ways:

**Option A: pipx install from PyPI (recommended — isolated environment, gives you the `learning-factory` command)**

```bash
pipx install learning-factory
```

**Option B: pipx install straight from GitHub (no local clone needed)**

```bash
pipx install git+https://github.com/Shoothedrifter/LearningFactory.git
```

**Option C: clone and pip install (development)**

```bash
git clone https://github.com/Shoothedrifter/LearningFactory.git
cd LearningFactory
pip install -r requirements.txt        # run directly (full dependencies)
# or
pip install -e ".[dev]"                # editable install + dev dependencies
```

> Dependency versions are governed by [pyproject.toml](pyproject.toml) (openai / httpx / python-dotenv / mcp / beautifulsoup4).

## Configuration

Create a `.env` file in the **working directory** (see [.env.example](.env.example) for reference) and put your API key in it (if your model provider is Zhipu GLM, it works out of the box):

```env
# Key page for the GLM provider, for example: https://bigmodel.cn → API keys
LLM_API_KEY="your-api-key-here"
```

You can also skip the `.env` file and export the variable directly: `export LLM_API_KEY="your-key"`.

Note: the program only loads `.env` from the **working directory** and never searches parent directories — when running from another directory, place a `.env` there. Without a key, startup prints instructions for obtaining and configuring one and exits immediately, instead of failing on the first API call.

**Switching to another OpenAI-compatible provider**: set `LLM_BASE_URL` to that provider's endpoint, and override `LLM_MAIN_MODEL` / `LLM_SUB_MODEL` / `LLM_REPO_MODEL` according to its model list. The three research tools (web search/fetch, repository reading) default to Zhipu's MCP services — when switching providers, switch the three `MCP_*_URL` variables as well (see "MCP endpoints for the research tools" below).

The minimal configuration for non-GLM providers is **4 variables** — `LLM_API_KEY` alone is not enough (the default endpoint and model names are all GLM: another provider's key gets a 401, and the model names clash). Taking Kimi and DeepSeek as examples (model names follow each provider's current list):

```env
# Kimi (Moonshot): https://platform.moonshot.cn → API Key management
LLM_API_KEY="<your Kimi key>"
LLM_BASE_URL="https://api.moonshot.cn/v1"
LLM_MAIN_MODEL="<fill in from Kimi's model list>"
LLM_SUB_MODEL="<fill in from Kimi's model list>"
LLM_REPO_MODEL="<fill in from Kimi's model list>"

# DeepSeek: https://platform.deepseek.com → API Keys
LLM_API_KEY="<your DeepSeek key>"
LLM_BASE_URL="https://api.deepseek.com/v1"
LLM_MAIN_MODEL="deepseek-chat"
LLM_SUB_MODEL="deepseek-chat"
LLM_REPO_MODEL="deepseek-chat"
```

**MCP endpoints for the research tools**: the three research tools default to Zhipu's MCP services, authenticated with the same `LLM_API_KEY` as the model API. If your provider also offers MCP services, point `MCP_WEB_SEARCH_URL` / `MCP_WEB_READER_URL` / `MCP_ZREAD_URL` at its endpoints (the key stays shared; set `MCP_API_KEY` only if the provider issues a separate key for MCP). If it doesn't offer MCP, the research tools are unavailable — main-agent orchestration, Notion tools, and local file I/O are unaffected.

All environment variables for model switching, MCP endpoint overrides, and more (put them in `.env` or export them directly):

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `LLM_API_KEY` | Yes | — (exits at startup if missing) | Model provider API key |
| `LLM_BASE_URL` | No | `https://open.bigmodel.cn/api/paas/v4/` | Provider's OpenAI-compatible endpoint (override for self-hosted proxies / compatible gateways) |
| `LLM_MAIN_MODEL` | No | `glm-5` | Main agent model |
| `LLM_SUB_MODEL` | No | `glm-5-turbo` | General sub-agent model (docs_researcher / web_researcher / file_writer) |
| `LLM_REPO_MODEL` | No | `glm-5` | Dedicated model for repo_analyzer |
| `MCP_API_KEY` | No | Falls back to `LLM_API_KEY` | Separate auth for MCP research tools (set when the provider issues a dedicated MCP key) |
| `MCP_WEB_SEARCH_URL` | No | `https://open.bigmodel.cn/api/mcp/web_search_prime/mcp` | MCP web search endpoint |
| `MCP_WEB_READER_URL` | No | `https://open.bigmodel.cn/api/mcp/web_reader/mcp` | MCP web fetch endpoint |
| `MCP_ZREAD_URL` | No | `https://open.bigmodel.cn/api/mcp/zread/mcp` | MCP GitHub repository reading endpoint |

## Running

**CLI mode (terminal interaction):**

```bash
learning-factory                          # entry command after pipx/pip install
# or (clone scenario, not installed)
python -m learning_factory.agent
```

- Type `exit` to quit; type `clear` to reset the conversation history
- `--resume`: resume the last session; or pass a path: `--resume ~/.learning_factory/sessions/<file>.jsonl`
- `--output-dir <dir>`: root directory for generated artifacts (default `Learning-Factory/`)
- Progress is streamed live: sub-agent start/finish (`▶`/`✔`/`✖`) and each tool call are printed line by line, with the final answer printed as a whole

## Session Persistence (CLI)

In CLI mode, conversation history is written turn by turn to `~/.learning_factory/sessions/` in the home directory (JSONL format, flushed to disk immediately with no buffering), so turns already written survive a crash; with pipx, sessions started from any directory land in the same place.

- `--resume`: resume the most recent session; `--resume <file path>` resumes a specific session
- On resume, trailing unanswered messages are trimmed automatically; if no resumable session is found, a new one starts
- Typing `clear` starts a new session file; the old session file is kept

## More Documentation

Architecture design (agent collaboration / ReAct loop), tool system and assignment, MCP integration, the skill system, the full environment variable table, and the mapping to the original claude_agent_sdk — all in **[AGENT.md](AGENT.md)** (in Chinese).

## Development & Testing

```bash
pip install -r requirements-dev.txt
pytest    # 145 tests, fully mocked, no real API key needed
```

## Notes

- The Bash tool executes commands on your machine — run only in a trusted environment
- `.env` contains API keys and must not be committed to version control
- Directories like `Learning-Factory/learning-pytorch/` are system-generated artifacts (git-ignored, never committed)

## License

[MIT](LICENSE)
