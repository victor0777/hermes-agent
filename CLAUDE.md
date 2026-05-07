# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Hermes Agent is a self-improving AI agent by Nous Research. It features a learning loop (skills from experience, persistent memory, session search), runs on any LLM provider via OpenAI-compatible APIs, and connects through CLI, Telegram, Discord, Slack, WhatsApp, Signal, and more.

## Git Repository

- **Origin**: https://github.com/NousResearch/hermes-agent.git (fork: victor0777)

## Development Setup

```bash
uv venv venv --python 3.11
source venv/bin/activate          # ALWAYS activate before running Python
uv pip install -e ".[all,dev]"
```

User config lives in `~/.hermes/` (config.yaml, .env, skills/, memories/, state.db, sessions/).

## Common Commands

```bash
# Run tests (unit only, parallel by default via pytest-xdist)
python -m pytest tests/ -q                          # Full suite (~3000 tests)
python -m pytest tests/test_model_tools.py -q       # Single file
python -m pytest tests/test_model_tools.py::test_name -q  # Single test
python -m pytest -m integration tests/              # Integration tests (need API keys)

# Run the agent
hermes                    # Interactive CLI
hermes gateway start      # Messaging gateway
hermes doctor             # Diagnostics
```

pytest config: `testpaths = ["tests"]`, default excludes `integration` marker, runs with `-n auto`.

## Architecture

### Core Loop

```
User message → AIAgent.run_conversation() (run_agent.py)
  → prompt_builder.py assembles system prompt
  → LLM call (OpenAI-compatible API)
  → tool_calls? → registry dispatch → loop back
  → text response? → persist to SessionDB → return
```

### File Dependency Chain

```
tools/registry.py  (no deps — imported by all tool files)
       ↑
tools/*.py  (each calls registry.register() at import time)
       ↑
model_tools.py  (imports tools/registry + triggers tool discovery via _discover_tools())
       ↑
run_agent.py, cli.py, batch_runner.py, environments/
```

### Key Modules

| Module | Role |
|--------|------|
| `run_agent.py` | `AIAgent` class — core conversation loop, tool dispatch, session persistence |
| `cli.py` | `HermesCLI` — interactive TUI (Rich + prompt_toolkit) |
| `model_tools.py` | Tool orchestration, `_discover_tools()`, `handle_function_call()` |
| `toolsets.py` | Tool groupings/presets (`_HERMES_CORE_TOOLS`), per-platform toolset config |
| `hermes_state.py` | `SessionDB` — SQLite with FTS5 full-text search |
| `hermes_constants.py` | `get_hermes_home()`, `display_hermes_home()` — profile-aware path resolution |
| `agent/prompt_builder.py` | System prompt assembly (identity, skills, context files, memory) |
| `agent/context_compressor.py` | Auto-summarization when approaching context limits |
| `hermes_cli/commands.py` | Central `COMMAND_REGISTRY` — all slash commands defined here |
| `hermes_cli/config.py` | `DEFAULT_CONFIG`, `OPTIONAL_ENV_VARS`, config migration |
| `gateway/run.py` | `GatewayRunner` — platform lifecycle, message routing |
| `tools/registry.py` | Central tool registry (schemas, handlers, dispatch) |

### Design Patterns

- **Self-registering tools**: Each `tools/*.py` calls `registry.register()` at import time. `model_tools.py` triggers discovery.
- **Toolset grouping**: Tools grouped into toolsets (web, terminal, file, browser, etc.) enabled/disabled per platform.
- **Ephemeral injection**: System prompts injected at API call time, never persisted to DB/logs.
- **Provider abstraction**: Any OpenAI-compatible API. Provider resolved at init time.
- **Slash command registry**: All commands defined as `CommandDef` in `hermes_cli/commands.py`. CLI dispatch, gateway dispatch, Telegram menus, Slack routing, and autocomplete all derive from this single registry.

## Adding Things

### New Tool (3 files)

1. Create `tools/your_tool.py` — schema + handler + `registry.register()` call
2. Add import in `model_tools.py` `_discover_tools()` list
3. Add to `toolsets.py` — either `_HERMES_CORE_TOOLS` or a new toolset

All handlers MUST return a JSON string. Use `get_hermes_home()` for state files, never `Path.home() / ".hermes"`.

### New Slash Command

1. Add `CommandDef` to `COMMAND_REGISTRY` in `hermes_cli/commands.py`
2. Add handler in `HermesCLI.process_command()` in `cli.py`
3. If gateway-available, add handler in `gateway/run.py`

Adding an alias only requires modifying the `aliases` tuple on the existing `CommandDef`.

### New Config Option

1. Add to `DEFAULT_CONFIG` in `hermes_cli/config.py`
2. Bump `_config_version` to trigger migration

### Skill vs Tool Decision

Almost always make it a **skill** (in `skills/` or `optional-skills/`). Only make a tool when it requires custom Python integration, binary data handling, or precise execution guarantees.

## Known Pitfalls

- **NEVER hardcode `~/.hermes` paths** — use `get_hermes_home()` for code, `display_hermes_home()` for user-facing messages. Hardcoding breaks profiles.
- **DO NOT use `simple_term_menu`** — rendering bugs in tmux/iTerm2. Use `curses` instead (see `hermes_cli/tools_config.py`).
- **DO NOT use `\033[K`** (ANSI erase-to-EOL) in spinner/display — leaks as `?[K` under prompt_toolkit's `patch_stdout`. Use space-padding.
- **DO NOT hardcode cross-tool references in schema descriptions** — tools from other toolsets may be unavailable. Add cross-references dynamically in `get_tool_definitions()` in `model_tools.py`.
- **Prompt caching must not break** — do NOT alter past context, change toolsets, reload memories, or rebuild system prompts mid-conversation. Only context compression may alter context.
- **`_last_resolved_tool_names`** is a process-global in `model_tools.py` — saved/restored around subagent execution in `delegate_tool.py`.
- **Tests must not write to `~/.hermes/`** — the `_isolate_hermes_home` autouse fixture in `tests/conftest.py` redirects to a temp dir. When testing profiles, also mock `Path.home()`.
- **Path references in tool schemas**: Use `display_hermes_home()` for file paths in schema descriptions (resolved after profile override).

## Code Style

- PEP 8, no strict line length enforcement
- Comments only for non-obvious intent, trade-offs, or API quirks
- Catch specific exceptions; log with `logger.warning()`/`logger.error()`, use `exc_info=True` for unexpected errors
- Cross-platform: never assume Unix
