# PCB System Backend

FastAPI 后端：管理项目、启动 Claude 子进程、流式转发 stream-json、监听 markdown 文件变化。

## 安装

```bash
cd pcb-system/backend
python -m venv .venv
source .venv/bin/activate         # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

确保系统已安装 Claude Code CLI（`claude` 命令在 PATH 里）。如果不在，设环境变量 `CLAUDE_BIN=/path/to/claude`。

## 启动

从 `pcb-system/` 根目录跑（**不是** backend 子目录）：

```bash
cd pcb-system
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
| GET | `/health` | 存活探测 |
| GET | `/projects` | 项目列表 |
| POST | `/projects` `{name}` | 创建项目（init workdir + git + 拷 prompts） |
| GET | `/projects/{id}` | 项目详情 + 文件列表 + active_run 标志 |
| DELETE | `/projects/{id}` | 删除项目（含 workdir） |
| GET | `/projects/{id}/files/{fname}` | 读 phase 文件原文 |
| GET | `/projects/{id}/runs` | run 历史 |
| POST | `/projects/{id}/runs` `{message}` | 启动一次 Claude run（202 Accepted，立刻返回） |
| GET | `/projects/{id}/messages?since=N` | 拉历史 stream-json 消息 |

### WebSocket

```
ws://localhost:8000/ws/projects/{project_id}?since=0
```

握手后立刻：
1. 重放 `seq > since` 的历史消息
2. 推 `{"type":"ws_ready", ...}` 标志重放结束
3. 持续推 live 事件：
   - Claude stream-json 消息（`text_delta` / `tool_use` / `tool_result` / ...）
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

- `pcb-system/projects/<project-id>/` — 每个项目的 workdir（含 .git）
- `pcb-system/data/pcb.sqlite` — 元数据（项目、runs、messages）
- `pcb-system/backend/prompts/` — orchestrator + subagents（每次 run 启动前拷贝到项目）

修改 `backend/prompts/` 下的 .md，下次任意 run 启动会自动用新版（已有项目无需迁移）。
