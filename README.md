# WeaveAI 智能分析助手

WeaveAI 2.0：Supervisor-Worker + 多轮辩论 的多 Agent 市场洞察系统（SSE 实时流式输出）。

---

## 目录结构

```text
WeaveAI/
├── backend/
│   ├── main.py             # FastAPI 入口
│   ├── core/               # 配置、Ark 客户端封装、LangGraph 引擎
│   ├── agents/             # 专业 Agent（趋势/竞品/法规/社媒/综合）
│   ├── routers/v2/         # v2 API（/api/v2/market-insight/...）
│   ├── schemas/v2/         # v2 请求/响应/SSE 事件协议
│   └── requirements.txt    # WeaveAI 2.0 依赖
└── frontend/
    ├── app/
    │   ├── page.js         # v2 工作流 UI（SSE）
    │   ├── layout.js       # 注入 WorkflowProvider
    │   └── components/     # ProfileForm / Sidebar / Modal 等
    ├── globals.css         # Tailwind 基础样式（暗色）
    ├── package.json        # 前端依赖
    ├── tailwind.config.mjs # Tailwind 配置
    ├── next.config.mjs     # Next.js 配置
    └── .env.local          # NEXT_PUBLIC_API_BASE_URL
```

---

## 技术栈

- 前端：Next.js (React)、Tailwind CSS、react-markdown + remark-gfm。
- 后端：FastAPI、LangGraph、火山引擎 Ark Responses API（web_search / thinking）、Supabase（可选）。

---

## 快速开始（本地）

### 1) 后端
```bash
cd backend
uv venv .venv
uv pip install -r requirements.txt

# Windows PowerShell: 设置环境变量（也可写入 backend/.env）
# $env:ARK_API_KEY="你的ArkKey"

python.exe -m uvicorn main:app --port 8000 # 生产模式
python.exe -m uvicorn main:app --reload --port 8000 # 开发模式
```

### 2) 前端
```bash
cd frontend
npm install
echo NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000 > .env.local
npm run dev  # 默认 http://localhost:3000
```

---

## 后端 API 快览

### 健康检查
- `GET /health`
- `GET /api/v2/market-insight/health`

### 市场洞察（v2）
- `POST /api/v2/market-insight/stream`：SSE 流式输出（推荐）
- `POST /api/v2/market-insight/generate`：非流式一次性返回

请求体（示例）：
```json
{
  "profile": {
    "target_market": "Germany",
    "supply_chain": "Consumer Electronics",
    "seller_type": "品牌方",
    "min_price": 30,
    "max_price": 90
  },
  "debate_rounds": 2,
  "enable_followup": true,
  "enable_websearch": true
}
```

---

## 前端
前端页面直接调用 v2 SSE 接口并展示：
- 多 Agent 执行进度（agent_start/agent_chunk/agent_end）
- 辩论轮次事件（debate_round_start/...）
- 最终综合报告（orchestrator_end.final_report）

---

## 环境变量

| 文件 | 变量 | 说明 |
| --- | --- | --- |
| backend/.env | `ARK_API_KEY`（建议） | 火山引擎 Ark API Key（未配置也可启动健康检查，但调用模型会失败） |
| frontend/.env.local | `NEXT_PUBLIC_API_BASE_URL` | 后端地址，例如 `http://127.0.0.1:8000` |

依赖清单详见 `backend/requirements.txt`。

---

## FAQ
- 启动后访问不到接口？确认前端 `NEXT_PUBLIC_API_BASE_URL` 指向后端地址。
- SSE 没有输出？检查后端控制台日志，确认已配置 `ARK_API_KEY` 且网络可用。

---

## Phase 5 路演资产

- Demo Script（3~5 分钟话术与现场操作）：`PHASE5_DEMO_SCRIPT.md`
- 评委 FAQ（高频追问标准回答）：`PHASE5_FAQ.md`
- 竞品差异一页纸：`PHASE5_COMPETITOR_ONEPAGER.md`
- 风险应答与现场处置：`PHASE5_RISK_RESPONSE.md`
- 跑通验收记录（当前阶段结论与命令）：`PHASE5_ACCEPTANCE.md`

---

## 贡献 & 许可
- 建议先跑通：`/api/v2/market-insight/stream` 的完整工作流（含 agent 事件与最终报告）。若改动前端交互，保持 SSE 事件解析与渲染链路可用。  
- 许可证：MIT（如团队有要求可替换）。

---

## 源码对照
- API 入口：`backend/main.py`
- LangGraph 工作流：`backend/core/graph_engine.py`
- v2 SSE 端点：`backend/routers/v2/market_insight.py`
- 前端工作流与 SSE 解析：`frontend/hooks/useStreamV2.js`、`frontend/app/page.js`
