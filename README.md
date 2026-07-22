# 知识路径学习 Demo

根据学习目标生成前置知识依赖图，支持五档掌握度自评，并生成补缺学习路径。

## 要求

1. Python ≥ 3.12
2. [uv](https://docs.astral.sh/uv/)
3. Node.js 与 pnpm
4. 任意兼容 **OpenAI Chat Completions**（`/v1/chat/completions`）的网关

## 安装与运行

```bash
uv sync --extra dev
cd frontend
pnpm install
pnpm build
cd ..

# 可选：服务端默认密钥；也可仅在网页填写
export OPENAI_API_KEY=sk-xxx
export OPENAI_BASE_URL=https://api.openai.com/v1
export OPENAI_MODEL=gpt-4o-mini
# 可选默认思考与窗口
export LLM_REASONING_EFFORT=none   # none|low|medium|high
export LLM_MAX_TOKENS=0            # 0 表示不发送 max_tokens
export LLM_ENABLE_THINKING=false
uv run knowledge-path-demo
```

浏览器打开 http://127.0.0.1:8000

前端开发模式：

```bash
# 先在项目根目录启动 FastAPI，再开启 Vite 开发服务器
cd frontend
pnpm dev
```

Vite 会将 `/api` 请求代理到 `http://127.0.0.1:8000`。

页面「模型配置」可自定义：

1. API Key / Base URL / 模型名
2. 思考强度 `reasoning_effort` 与 `enable_thinking`
3. 输出 Token 上限（同时发送 `max_tokens` 与 `max_completion_tokens`）
4. temperature

配置保存在浏览器 `localStorage`，生成图/路径时随请求提交，**不写入服务端数据库**。

## 测试

后端测试导入应用时要求前端构建产物已经存在。清洁检出后应执行完整命令：

```bash
cd frontend
pnpm install
pnpm build
cd ..
uv run pytest -q
```

## 配置环境变量

| 变量                 | 说明                      |
| -------------------- | ------------------------- |
| OPENAI_API_KEY       | 服务端默认密钥            |
| OPENAI_BASE_URL      | 默认 Base URL             |
| OPENAI_MODEL         | 默认模型                  |
| LLM_REASONING_EFFORT | none/low/medium/high      |
| LLM_MAX_TOKENS       | 默认输出上限，0 不发送    |
| LLM_ENABLE_THINKING  | true/false                |
| GRAPH_MAX_NODES      | 依赖图最大节点数，默认 80 |
| GRAPH_MAX_DEPTH      | 依赖图最大深度，默认 24   |
| DATABASE_PATH        | SQLite 路径               |
