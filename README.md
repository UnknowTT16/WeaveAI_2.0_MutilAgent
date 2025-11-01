# 📈 WeaveAI 智能分析助手

> 告别感觉，让数据与 AI 为您引航。  
> 一个把「机会洞察 → 数据验证 → 行动计划 → 一键导出报告」整合到同一工作台的前后端一体化项目。

WeaveAI 面向跨境卖家与品牌团队，支持：
- **🤖 机会洞察（Insight）**：基于「战略档案」自动生成市场洞察，前端实时渲染思考过程与 Markdown 报告。
- **📊 自我验证（Validation）**：上传**销售/评论**数据，内置 LSTM 预测、KMeans 聚类、Apriori 购物篮分析、VADER 情感分析等。
- **🚀 行动计划（Action）**：把洞察 + 验证摘要 + 评论洞察合并，生成可落地的季度路线图，并可**一键导出 HTML 报表**（保存在后端静态目录可直接分享）。

---

## 📁 目录结构

```text
WeaveAI/
├── backend/
│   ├── main.py              # FastAPI 入口、路由与静态导出逻辑
│   ├── WAIapp_core.py       # AI 生成与数据分析核心、最终 HTML 报告模板
│   ├── requirements.txt     # Python 依赖清单
│   ├── static/
│   │   └── reports/         # 已生成的 HTML 报告（通过 /reports/ 访问）
│   └── .env                 # ARK_API_KEY 等后端环境变量
└── frontend/
    ├── app/
    │   ├── page.js          # 三步工作流主视图与状态
    │   ├── layout.js        # 根布局（字体、样式注入）
    │   ├── globals.css      # Tailwind 基础样式（暗色系）
    │   └── components/      # ReportDisplay / ValidationDashboard / ActionPlanner / ...
    ├── package.json         # 前端依赖
    ├── tailwind.config.mjs  # Tailwind 配置（含 typography 插件）
    ├── next.config.mjs      # Next.js 配置
    └── .env.local           # NEXT_PUBLIC_API_BASE_URL
```

参考：后端挂载静态目录 `/reports`、数据模型与各 API 定义、静态样式与白底图表导出等实现已在仓库源码中体现。

---

## 🛠️ 技术栈

**Frontend（Next.js + React）**
- Tailwind CSS（含 `@tailwindcss/typography`），暗色系 UI 基调；
- 可视化：`plotly.js` / `react-plotly.js`（客户端动态加载）。
- Markdown 渲染：`react-markdown` + `remark-gfm`（统一在 UI 中安全展示）。

**Backend（FastAPI）**
- 路由：流式生成洞察/行动计划/评论摘要、静态导出 HTML 报告；
- 数据分析：Pandas / NumPy、Scikit-learn（KMeans）、TensorFlow（LSTM）、VaderSentiment、mlxtend（Apriori）等。依赖见 `requirements.txt`。

---

## 🚀 快速开始（本地开发）

### 1) 启动 Backend（FastAPI）

```bash
cd backend
python -m venv venv
# macOS / Linux
source venv/bin/activate
# Windows
venv\Scripts\Activate.ps1

pip install -r requirements.txt
# 写入你在火山引擎 Ark 的密钥
echo ARK_API_KEY="你的ArkKey" > .env

# 启动服务：默认 http://127.0.0.1:8000
uvicorn main:app --reload
```

> 首次运行会自动创建并挂载 `static/reports` 目录用于存放 HTML 报告，可通过 `http://127.0.0.1:8000/reports/xxx.html` 直接访问。

### 2) 启动 Frontend（Next.js）

```bash
cd frontend
npm install
echo NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000 > .env.local

# dev 启动：默认 http://localhost:3000
npm run dev
```

---

## 📡 后端 API 一览

### AI 报告（流式返回 `text/plain`）
| Endpoint | 描述 | 请求体关键字段 |
|---|---|---|
| `POST /api/v1/reports/market-insight` | 生成市场洞察（含思考过程与 Markdown 报告流式输出） | `target_market` `supply_chain` `seller_type` `min_price` `max_price` |
| `POST /api/v1/reports/action-plan` | 生成行动计划（将洞察与验证摘要合并） | `market_report` `validation_summary` |
| `POST /api/v1/reports/review-summary` | 评论洞察摘要（基于正/负样本） | `positive_reviews` `negative_reviews` |

### 数据分析（返回 JSON）
| Endpoint | 功能 | 上传内容 |
|---|---|---|
| `POST /api/v1/data/forecast-sales` | LSTM 销售预测，返回 Plotly JSON | 销售数据（`.csv/.parquet`） |
| `POST /api/v1/data/product-clustering` | KMeans 聚类 + 购物篮分析，返回簇摘要/商品点/图表 JSON | 销售数据（`.csv/.parquet`） |
| `POST /api/v1/data/sentiment-analysis` | 评论情感分析，返回评分与精选样本 | 评论数据（`.csv/.parquet`） |

> **说明**：旧 README 中提到的 `POST /api/v1/reports/export-pdf` **当前未在后端实现**，请以本节表格与 `main.py` 源码为准。

---

## 🧭 前端工作流（3 步）

1. **机会洞察**：提交“战略档案”后，前端通过 `ReportDisplay` 组件与后端 `/market-insight` 建立流式连接，实时渲染**思考过程**与**正式报告**。
2. **数据验证**：在 `ValidationDashboard` 上传销售/评论数据，调用后端三个数据分析端点，并将结果回传给父级 `page.js` 汇总为**验证摘要**。
3. **行动计划与导出**：`ActionPlanner` 调用 `/action-plan` 生成 Markdown 版行动计划；随后把洞察、验证摘要和图表 JSON 传给 `/generate-and-save-report` 生成**可视化 HTML 报告**（后端静态 URL 可分享）。

---

## 🧪 请求示例

### 1) 生成市场洞察（流式）
```bash
curl -N -X POST http://127.0.0.1:8000/api/v1/reports/market-insight   -H "Content-Type: application/json"   -d '{
    "target_market": "DE",
    "supply_chain": "FBA",
    "seller_type": "Brand",
    "min_price": 30,
    "max_price": 90
  }'
```

### 2) LSTM 销售预测（上传 CSV）
```bash
curl -X POST http://127.0.0.1:8000/api/v1/data/forecast-sales   -F "file=@sales.csv"
```

### 3) 生成最终 HTML 报告（整合导出）
```bash
curl -X POST http://127.0.0.1:8000/api/v1/reports/generate-and-save-report   -H "Content-Type: application/json"   -d '{
    "market_report": "...(Markdown)...",
    "validation_summary": "内部数据验证要点…",
    "action_plan": "...(Markdown)...",
    "forecast_chart_json": "{...}",
    "clustering_data": {"cluster_summary": [...], "product_points": [...]},
    "elbow_chart_json": "{...}",
    "scatter_3d_chart_json": "{...}",
    "basket_analysis_data": [...]
  }'
```

成功后返回：
```json
{ "report_url": "http://127.0.0.1:8000/reports/report_xxx.html" }
```

---

## 🎨 报告样式与图表底色

- 最终导出的 HTML 报告使用**暗色主题**正文，但关键图表（手肘图、3D 聚类）在导出时强制**白底**，保证打印/分享可读性。实现方式：Plotly `template='plotly_white'` + `paper_bgcolor/plot_bgcolor` 强制白色。  
- HTML 报告模板包含标题、三大章节、表格样式、页脚时间戳等，样式统一封装在 `WAIapp_core.py`。

---

## 🔑 环境变量

| 文件 | 变量 | 说明 |
|---|---|---|
| `backend/.env` | `ARK_API_KEY` | 必填：火山引擎 Ark API Key |
| （可选） | `CHROME_PATH` | 指向本机 Chrome/Edge，可用于后续接入 PDF 导出 |
| `frontend/.env.local` | `NEXT_PUBLIC_API_BASE_URL` | 前端访问的后端地址（如 `http://127.0.0.1:8000`） |

> 依赖清单见 `requirements.txt`（FastAPI / Pandas / scikit-learn / TensorFlow / VaderSentiment / mlxtend / Plotly / PyArrow / OpenPyXL / markdown2 / pandarallel / volcengine-ark 等）。

---

## 🧰 常见问题（FAQ）

- **为什么导出后能直接分享？**  
  后端把 HTML 报告写入 `static/reports/` 并挂载为 `/reports` 静态目录，返回可直接访问的 URL。

- **为什么我的图表是白底而页面是暗色？**  
  为保证打印/分享，对关键图表运行时强制白底（白纸打印更友好）。实现细节见 `WAIapp_core.py`。

- **README 里以前提过有 `/export-pdf` 吗？**  
  旧说明里提到过，但当前后端未实现该端点，请以 `main.py` 为准。

---

## 🤝 贡献

欢迎 PR 与 Issue！建议在提交前先跑通：
1. 三个流式/分析端点最小样例；
2. 生成一次最终 HTML 报告并在浏览器打开验证；
3. 若改动前端交互，确保 `page.js / components/*` 的状态流转一致（见源码）。

---

## 📜 许可证

MIT（可按团队要求替换）。

---

### 依据仓库源文件（可溯源片段）

- 后端 API 与静态导出逻辑：`backend/main.py`。  
- 最终 HTML 报告模板与图表白底控制：`backend/WAIapp_core.py`。  
- 前端流式渲染与调用关系：`frontend/app/components/ReportDisplay.js`、`ValidationDashboard.js`、`ActionPlanner.js`、`page.js`。  
- 样式与主题：`tailwind.config.mjs`、`globals.css`。  
- 依赖清单：`requirements.txt`。
