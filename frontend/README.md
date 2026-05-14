# PCB System Frontend

React + Vite + TypeScript 前端。三栏布局：项目列表 / 聊天+Phase 进度 / markdown 预览。

## 启动

```bash
cd pcb-system/frontend
npm install
npm run dev
# → http://localhost:5173
```

要求 backend 同时在 `http://localhost:8000` 跑。Vite 会代理 `/api/*` 和 `/ws/*` 到后端。

## 用法

1. 左侧栏点 **+ 新建** → 输入项目名（建议 ASCII，避免路径问题）
2. 选中项目后中栏下方输入框输入需求 → **发送**（或 Cmd/Ctrl+Enter）
3. 右栏 tab 切换 phase 文件，markdown 实时刷新
4. 顶部 phase 进度条显示当前进度（绿=完成 / 蓝=运行中 / 黄=等用户确认 / 灰=未开始）
5. 当 phase bar 显示"等待确认"时，输入"确认"或"继续"推进到下一阶段；输入修改类消息会触发 change-analyzer 回退

## 三栏

```
┌────────────┬───────────────────────┬─────────────────┐
│ ProjectList│ PhaseProgress (顶)    │ MarkdownPreview │
│            ├───────────────────────┤ (FileTabs +     │
│ + 新建     │ ChatPanel (流式消息)  │  react-markdown)│
│ × 删除     │   ↳ ToolUseCard       │                 │
│            │   ↳ Agent 卡 (蓝色)   │                 │
│            ├───────────────────────┤                 │
│            │ Input + 发送          │                 │
└────────────┴───────────────────────┴─────────────────┘
```

## 关键组件

| 文件 | 行数 | 职责 |
|---|---|---|
| `App.tsx` | ~50 | 三栏 + 状态分发 |
| `ws.ts` | ~190 | WS 连接 + stream-json → ChatItem 转换 + 自动重连 |
| `api.ts` | ~50 | HTTP 客户端封装 |
| `components/ProjectList.tsx` | ~110 | 项目 CRUD（TanStack Query） |
| `components/ChatPanel.tsx` | ~150 | 聊天流 + ToolUseCard + 输入框 |
| `components/PhaseProgress.tsx` | ~95 | 解析 brief.md YAML frontmatter + 7 段进度条 |
| `components/MarkdownPreview.tsx` | ~80 | FileTabs + react-markdown + KaTeX |
| `styles.css` | ~390 | 全部样式（无 framework） |
| `types.ts` | ~150 | 共享类型 |

## WebSocket 事件流处理

WS hook 把 stream-json 流转成扁平的 `ChatItem[]`：

| 来源事件 | 渲染为 |
|---|---|
| `system` (subtype=init) | `system` 行（灰）"Claude session started" |
| `assistant` 内 `text` | 助手气泡 |
| `assistant` 内 `tool_use` | ToolUseCard，初始"运行中" |
| `user` 内 `tool_result` | 匹配回对应 ToolUseCard，更新"完成/错误" |
| `result` | `system` 行（绿/红）显示结果 |
| `run_complete` | `system` 行 + 解锁输入框 |
| `file_updated` | 更新 `files` map → MarkdownPreview/PhaseProgress 重渲染 |
| `system_error` / `system_warning` | `system` 行 |

特别处理：
- `tool_use.name === "Task" || "Agent"` 显示为蓝色 Agent 卡，标题包含 `subagent_type`
- 默认折叠 tool_use input/result，点击展开
- 自动重连：WS 断开 2s 后重试，用 `since=lastSeq` 继续上次消息

## Build

```bash
npm run build
# 产出 dist/
```

构建产物 ~666 kB（gzip 206 kB），主要是 KaTeX。如果不用公式可以去掉 `rehype-katex` + `remark-math` 减一半。

## 依赖

| 包 | 用途 |
|---|---|
| react / react-dom | 18 |
| @tanstack/react-query | HTTP 状态 |
| react-markdown | markdown 渲染 |
| remark-gfm | 表格/任务列表 |
| remark-math + rehype-katex + katex | 数学公式（电路计算可能用到） |
| js-yaml | 解析 brief.md frontmatter |
| vite + @vitejs/plugin-react | 构建工具 |
