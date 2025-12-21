# WeaveAI 智能分析助手

> 告别感觉，让数据和 AI 为你导航 —— 「机会洞察 → 数据验证 → 行动计划 → 一键导出报告」的一体化工作台。

WeaveAI 面向跨境卖家与品牌团队，核心能力：
- 机会洞察：基于战略档案流式生成市场报告，支持可选 WebSearch。
- 数据验证：销售预测、KMeans 聚类 + 购物篮分析、异常监测、评论情感分析。
- 行动计划：合并洞察和验证摘要生成行动路线图，可导出 HTML 报告并一键 PDF。

---

## 目录结构

```text
WeaveAI/
├── backend/
│   ├── main.py             # FastAPI 入口、路由、静态导出与 PDF 导出
│   ├── WAIapp_core.py      # AI 生成与数据分析核心，最终 HTML 报告模板
│   ├── requirements.txt    # Python 依赖
│   ├── static/
│   │   └── reports/        # 生成的 HTML/PDF 报告（/reports/ 访问）
│   └── .env                # ARK_API_KEY、可选 CHROME_PATH
└── frontend/
    ├── app/
    │   ├── page.js         # 三步工作流主视图与状态
    │   ├── layout.js       # 全局布局与样式注入
    │   └── components/     # ReportDisplay / ValidationDashboard / ActionPlanner ...
    ├── globals.css         # Tailwind 基础样式（暗色）
    ├── package.json        # 前端依赖
    ├── tailwind.config.mjs # Tailwind 配置
    ├── next.config.mjs     # Next.js 配置
    └── .env.local          # NEXT_PUBLIC_API_BASE_URL
```

---

## 技术栈

- 前端：Next.js (React)、Tailwind CSS、react-plotly.js、react-markdown + remark-gfm。
- 后端：FastAPI、Pandas/NumPy、scikit-learn、TensorFlow (LSTM)、VaderSentiment、mlxtend (Apriori)、Plotly、pandarallel、volcengine-ark、pyppeteer (PDF)。

---

## 快速开始（本地）

### 1) 后端
```bash
cd backend
python -m venv venv
venv\Scripts\Activate.ps1  # Windows（或 source venv/bin/activate）
pip install -r requirements.txt
echo ARK_API_KEY="你的ArkKey" > .env
uvicorn main:app --reload  # 默认 http://127.0.0.1:8000
```
首次运行会自动创建并挂载 `static/reports` 目录，可直接通过 `http://127.0.0.1:8000/reports/xxx.html` 访问。

### 2) 前端
```bash
cd frontend
npm install
echo NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000 > .env.local
npm run dev  # 默认 http://localhost:3000
```

### 3) Docker（可选）
```bash
docker-compose up --build
```
`docker-compose.yml` 已挂载 `static/reports`，并示例了 `CHROME_PATH=/usr/bin/chromium`。

---

## 后端 API 快览

### AI 报告（流式 `text/plain`）
- `POST /api/v1/reports/market-insight`：生成市场洞察（字段：`target_market` `supply_chain` `seller_type` `min_price` `max_price`，可选 `use_websearch`）。
- `POST /api/v1/reports/action-plan`：基于洞察与验证摘要生成行动计划（`market_report` `validation_summary`）。
- `POST /api/v1/reports/review-summary`：评论洞察摘要（`positive_reviews` `negative_reviews`）。
- `POST /api/v1/reports/generate-and-save-report`：整合生成最终 HTML，返回 `report_url`。
- `POST /api/v1/reports/export-pdf`：把已生成的 HTML 报告转 PDF，返回 `pdf_url`（需本机 Chrome/Edge 或 pyppeteer）。

### 数据分析（JSON）
- `POST /api/v1/data/forecast-sales`：LSTM 销售预测，返回 Plotly JSON。
- `POST /api/v1/data/product-clustering`：KMeans 聚类 + 购物篮分析，返回簇摘要、3D 点位、手肘图 JSON。
- `POST /api/v1/data/anomaly-detection`：销量异常监测，返回时间序列、SKU 概览、Top 异常。
- `POST /api/v1/data/sentiment-analysis`：评论情感分析，自动识别评论列，返回评分与样本。

---

## 前端三步流
1) 机会洞察：在页面开启/关闭 WebSearch 后，流式展示思考过程与报告。  
2) 数据验证：上传销售/评论文件，四个 Tab：销售预测、深度数据挖掘（聚类 + 购物篮）、异常监测、情感分析。完成后生成“验证摘要”。  
3) 行动计划：生成行动计划 Markdown；可一键导出整合 HTML 报告，再调用 PDF 导出。

---

## 环境变量

| 文件 | 变量 | 说明 |
| --- | --- | --- |
| backend/.env | `ARK_API_KEY`（必填） | 火山引擎 Ark API Key |
| backend/.env | `CHROME_PATH`（可选） | 指向本机 Chrome/Edge 可执行，用于 PDF 导出优先使用本地浏览器 |
| frontend/.env.local | `NEXT_PUBLIC_API_BASE_URL` | 后端地址，例如 `http://127.0.0.1:8000` |

依赖清单详见 `backend/requirements.txt`。

---

## FAQ
- 为什么图表是白底、页面是暗色？关键图表导出时强制白底便于打印/分享，见 `WAIapp_core.py`。  
- PDF 导出失败怎么排查？在系统环境变量设置 `CHROME_PATH` 指向本机 Chrome/Edge（如 `C:\Program Files\Google\Chrome\Application\chrome.exe`），或检查容器内是否有 Chromium。  
- 报告在哪访问？后端写入 `static/reports` 并挂载 `/reports`，返回的 URL 可直接分享。

---

## 贡献 & 许可
- 建议先跑通：流式洞察、三类数据分析、生成一次 HTML 报告与 PDF。若改动前端交互，保持 `page.js` 与 `components/*` 状态流转一致。  
- 许可证：MIT（如团队有要求可替换）。

---

## 源码对照
- API 与静态导出：`backend/main.py`
- 报告模板与图表白底控制：`backend/WAIapp_core.py`
- 前端流式渲染与分析面板：`frontend/app/components/*.js`、`frontend/app/page.js`
- 样式：`frontend/app/layout.js`、`globals.css`、`tailwind.config.mjs`
