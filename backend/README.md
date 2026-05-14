# Voltaris Backend

FastAPI 后端：管理项目、按配置启动 AI 执行引擎（Claude Code 或 Codex CLI）、转发统一事件、监听 markdown 文件变化。

## 安装

```bash
cd Voltaris/backend
python -m venv .venv
source .venv/bin/activate         # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

默认执行引擎是 Claude Code。确保系统已安装 Claude Code CLI（`claude` 命令在 PATH 里）。如果不在，设环境变量 `CLAUDE_BIN=/path/to/claude`。

如需使用 Codex CLI，确保 `codex` 命令在 PATH 里，或设 `CODEX_BIN=/path/to/codex`。

## 执行引擎 Provider

通过环境变量选择执行引擎：

```bash
# 默认值，保持旧行为
export VOLTARIS_AGENT_PROVIDER=claude

# 使用 Codex CLI
export VOLTARIS_AGENT_PROVIDER=codex
```

Provider 边界在 `backend/providers/`：

- `ClaudeProvider` 负责 Claude Code 的命令参数、`stream-json` 解析和 `CLAUDE.md` / `.claude/agents` prompt 同步。
- `CodexProvider` 负责 Codex CLI 的 `codex exec --json` 参数、JSONL 解析和 `AGENTS.md` / `.codex/agents` / `.codex/refs` / `.codex/tools` 同步。
- `runner.py` 只负责 orchestration、run 状态、DB 消息、WebSocket fanout、取消和结束后的 git commit。

### Provider 配置

| 变量 | 默认值 | 说明 |
|---|---|---|
| `VOLTARIS_AGENT_PROVIDER` | `claude` | `claude` 或 `codex` |
| `CLAUDE_BIN` | `claude` | Claude Code CLI 路径 |
| `CLAUDE_SKIP_PERMISSIONS` | `true` | 为 Claude Code 添加 `--dangerously-skip-permissions`；部署环境必须自行限制 workdir |
| `CODEX_BIN` | `codex` | Codex CLI 路径 |
| `CODEX_MODEL` | 空 | 传给 `codex exec --model` |
| `CODEX_PROFILE` | 空 | 传给 `codex exec --profile` |
| `CODEX_SANDBOX` | `workspace-write` | 传给 `codex exec --sandbox` |
| `CODEX_APPROVAL_POLICY` | `never` | 传给 `codex exec --ask-for-approval` |
| `CODEX_EPHEMERAL` | `true` | 添加 `--ephemeral`，避免落本地 Codex 会话文件 |
| `CODEX_BYPASS_SANDBOX` | `false` | 显式设为 true 时才添加 `--dangerously-bypass-approvals-and-sandbox` |

### 安全边界

- 后端只把 provider 子进程的 cwd 设为项目 workdir。
- Provider 子进程只继承显式 allowlist 的环境变量，避免把整个服务进程环境暴露给 CLI。
- Claude 的默认兼容路径会跳过 Claude Code 自身权限提示，适合由 Voltaris 外层隔离 workdir 的部署；如需关闭，设 `CLAUDE_SKIP_PERMISSIONS=false`。
- Codex 默认使用 `workspace-write` sandbox 和 `never` approval policy，不默认绕过 sandbox；只有 `CODEX_BYPASS_SANDBOX=true` 时才启用危险绕过。
- 文件读取 API 仍限制在已知 phase 文件、`00_project_brief.md`、`CLAUDE.md`、`AGENTS.md`。

### Codex subagent 降级策略

Claude Code 支持 `Agent` 工具和 `.claude/agents` subagent 协议。Codex CLI 当前路径不依赖该协议；后端会生成 `AGENTS.md`，把 orchestrator 和所有 subagent 指令同步到 `.codex/agents/`，把 CircuitIR 参考文档同步到 `.codex/refs/`，把本地 helper 脚本同步到 `.codex/tools/`，并要求 Codex 在 orchestrator 需要调用 subagent 时按对应文件内联执行，一次只执行一个 subagent。这保留 7-phase 状态机和产出文件约定，但 Codex 前端事件不会显示 Claude 的 `Task` 工具卡片，而是显示 Codex CLI 可提供的 normalized tool/message 事件。

### 内部 WebSocket 事件

前端不依赖 provider 原始输出。Provider 输出会归一化为：

- `agent_session`：执行引擎会话开始
- `agent_message`：assistant 文本
- `agent_tool`：工具开始 / 完成
- `agent_result`：本次 run 的最终文本结果
- `agent_system`：info / warning / error
- `agent_raw`：无法识别但需要保留的原始行
- `run_complete`：后端完成清理、DB finish 和 git commit 后的结束事件

## 启动

从 `Voltaris/` 根目录跑（**不是** backend 子目录）：

```bash
cd Voltaris
python -m uvicorn backend.main:app --reload --port 8000
```

健康检查：

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

## API

### HTTP

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 存活探测 + 当前 `agent_provider` |
| GET | `/projects` | 项目列表 |
| POST | `/projects` `{name}` | 创建项目（init workdir + git + 拷 prompts） |
| GET | `/projects/{id}` | 项目详情 + 文件列表 + active_run 标志 + 当前 `agent_provider` |
| DELETE | `/projects/{id}` | 删除项目（含 workdir） |
| GET | `/projects/{id}/files/{fname}` | 读 phase 文件原文 |
| GET | `/projects/{id}/runs` | run 历史 |
| POST | `/projects/{id}/runs` `{message}` | 启动一次 provider run（202 Accepted，立刻返回） |
| GET | `/projects/{id}/messages?since=N` | 拉历史 normalized 消息 |

### WebSocket

```
ws://localhost:8000/ws/projects/{project_id}?since=0
```

握手后立刻：
1. 重放 `seq > since` 的历史消息
2. 推 `{"type":"ws_ready", ...}` 标志重放结束
3. 持续推 live 事件：
   - normalized provider 消息（`agent_message` / `agent_tool` / `agent_result` / ...）
   - `{"type":"file_updated","path":"01_requirements.md","content":"..."}`
   - `{"type":"file_deleted","path":"..."}`
   - `{"type":"run_complete","run_id":N,"exit_code":0}`

## 端到端冒烟测试

```bash
# 1. 创建项目
curl -s -XPOST http://localhost:8000/projects \
  -H 'content-type: application/json' \
  -d '{"name":"温控器测试"}' | jq

# 假设返回 id = "wenkongqi-ceshi-abc12345"

# 2. 一个终端起 WS 监听（需要 websocat 或 wscat）
websocat ws://localhost:8000/ws/projects/wenkongqi-ceshi-abc12345

# 3. 另一个终端启动一次 run
curl -s -XPOST http://localhost:8000/projects/wenkongqi-ceshi-abc12345/runs \
  -H 'content-type: application/json' \
  -d '{"message":"做一个 ESP32 温控器，4 路温度，蓝牙"}'

# WS 终端应该开始打印流式 JSON
```

## 数据存储

- `Voltaris/projects/<project-id>/` — 每个项目的 workdir（含 .git）
- `Voltaris/data/pcb.sqlite` — 元数据（项目、runs、messages）
- `Voltaris/backend/prompts/` — orchestrator + subagents（每次 run 启动前拷贝到项目）

修改 `backend/prompts/` 下的 .md，下次任意 run 启动会自动用新版（已有项目无需迁移）。
