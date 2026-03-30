# 评论分析功能实现方案

## Context

WeaveAI 2.0 现有的 Market Insight 是面向市场宏观维度的多 Agent 分析。本功能新增一个**微观维度**能力：输入网店评论页面 URL → 爬取评论数据 → 情感分析 → LLM 生成评论分析报告。补全"宏观市场洞察 + 微观用户声音"的完整分析链路。

**方案选择：**
- 平台范围：**Amazon + AliExpress**
- 爬取备选：**支持 CSV/JSON 上传**（爬取失败时的备选方案）
- 分析深度：**统计 + LLM 报告**（星级映射 + jieba 关键词 + Ark API 生成报告）
- 前端形式：**侧边栏新 Tab**
- 多语言策略：**中英文本地分词 + langdetect 检测语种 + 其他小语种关键词由 LLM 兜底**

---

## 一、关键边界与风险

### 1. 爬虫是最大的不确定性

| 边界 | 说明 |
|------|------|
| **平台差异** | Amazon 和 AliExpress HTML 结构完全不同，需要各自独立的 parser |
| **JS 渲染** | 两个平台评论区都是 JS 动态加载，需要 Playwright 无头浏览器 |
| **反爬** | User-Agent 检测、频率限制、验证码、IP 封禁 |
| **法律风险** | Amazon/AliExpress ToS 禁止自动化爬取，需用户知情同意 + CSV 上传备选 |
| **分页** | 控制爬取页数上限 10 页 ≈ 100 条评论 |
| **资源消耗** | Playwright 每实例 ~300MB 内存，严格单并发 |

### 2. 多语言评论处理

跨境电商评论涉及多种语言：

| 平台 | 评论语言分布 |
|------|-------------|
| Amazon.com | 英语为主，少量西班牙语 |
| Amazon.de | 德语为主，部分英语 |
| Amazon.co.jp | 日语为主 |
| AliExpress | **最复杂** — 英语、俄语、西班牙语、葡萄牙语、法语、阿拉伯语等混杂 |

**处理策略：**
- `langdetect` 逐条检测评论语言
- 星级 → 情感映射：语言无关，1-5 星在所有平台通用
- 关键词提取分语言处理：
  - 中文 (`zh`)：`jieba` 分词 → 词频 Top 20
  - 英文 (`en`)：空格分词 + 停用词过滤 → 词频 Top 20
  - 其他语种（德/日/俄/西/法等）：本地不提取关键词，在 LLM 报告生成时由模型一并分析
- LLM（Ark API 的 doubao/kimi/deepseek）天然支持多语言输入，报告生成无语言障碍

### 3. LLM 报告的 token 限制

- 100 条评论 × 平均 100 字 ≈ 15,000 tokens → `kimi-k2-thinking-251104` 上下文窗口足够
- 超过 80 条评论时采样：保留所有 1 星 + 所有 5 星 + 随机抽取 2-4 星

---

## 二、技术方案

### 2.1 后端新增/修改文件

```
backend/
  core/
    review_crawler.py          # 新建 - 爬虫核心：Playwright + 平台 parser
    review_processor.py        # 新建 - 统计分析：星级分布、关键词、情感映射
    review_engine.py           # 新建 - LangGraph StateGraph：crawl → process → report
  agents/
    review/
      __init__.py              # 新建
      review_analyst.py        # 新建 - ReviewAnalystAgent（继承 BaseAgent）
  routers/
    v2/
      __init__.py              # 修改 - 注册 review_analysis router
      review_analysis.py       # 新建 - API 端点：/stream, /upload, /status, /health
  schemas/
    v2/
      review_schemas.py        # 新建 - 请求/响应/事件模型
  database/
    migrations/
      006_review_analysis.sql  # 新建 - review_sessions 表
  requirements.txt             # 修改 - 新增 playwright, beautifulsoup4, jieba, langdetect
  Dockerfile                   # 修改 - 追加 playwright install chromium
```

### 2.2 LangGraph 工作流（3 节点，线性）

```
START → crawl_reviews → process_reviews → generate_report → END
```

**State 定义：**
```python
class ReviewAnalysisState(TypedDict, total=False):
    session_id: str
    url: Optional[str]          # URL 模式
    upload_data: Optional[list] # 上传模式（CSV/JSON 解析后的评论列表）
    input_mode: str             # "url" / "upload"
    platform: str               # "amazon" / "aliexpress" / "upload"（自动检测）
    max_pages: int

    # 爬取输出
    raw_reviews: list[dict]     # [{text, title, rating, date, verified, language, ...}]
    product_info: dict          # {name, asin/product_id, image_url, ...}
    crawl_error: Optional[str]

    # 分析输出
    analysis_data: dict         # ReviewAnalysisData 序列化

    # 报告输出
    report: Optional[str]       # Markdown 报告
    report_html_url: Optional[str]

    phase: str                  # crawl / process / report / complete / failed
    error: Optional[str]
```

**SSE 事件流：**
- `crawl_start` → `crawl_progress`(page N/M, reviews_so_far) → `crawl_complete` / `crawl_error`
- `analysis_start` → `analysis_complete`(sentiment_distribution, language_distribution, top_keywords)
- `report_start` → `report_chunk`(content) → `report_complete`(report_html_url)

### 2.3 爬虫模块 (`core/review_crawler.py`)

```python
class ReviewCrawler:
    """Playwright 无头浏览器爬取评论，支持多平台"""
    async def crawl(self, url: str, platform: str, max_pages: int, on_progress: Callable) -> CrawlResult

class BaseReviewParser(ABC):
    """平台 parser 基类"""
    @abstractmethod
    def parse_reviews(self, html: str) -> list[RawReview]: ...
    @abstractmethod
    def parse_product_info(self, html: str) -> ProductInfo: ...
    @abstractmethod
    def get_review_page_url(self, base_url: str, page: int) -> str: ...

class AmazonReviewParser(BaseReviewParser):
    """Amazon 评论解析 - 提取 title, text, rating, date, verified"""

class AliExpressReviewParser(BaseReviewParser):
    """AliExpress 评论解析 - 提取 text, rating, date, images"""

def detect_platform(url: str) -> str:
    """从 URL 自动检测平台：amazon.com/.co.uk/.de → 'amazon', aliexpress.com → 'aliexpress'"""
```

**反爬策略：**
- `playwright-stealth` 绕过无头检测
- User-Agent 轮换池（10-20 个真实浏览器 UA）
- 随机 2-5 秒页间延迟
- 120 秒硬超时
- 每次请求新建 browser context

### 2.4 CSV/JSON 上传支持

API 端点 `POST /api/v2/review-analysis/upload` 接受 multipart file：
- CSV 格式：要求列 `text`, `rating`(可选), `date`(可选)
- JSON 格式：`[{"text": "...", "rating": 5, "date": "2025-01-01"}, ...]`
- 解析后直接进入 `process_reviews` → `generate_report` 节点，跳过爬取

### 2.5 统计分析模块 (`core/review_processor.py`)

```python
@dataclass
class ReviewAnalysisData:
    total_reviews: int
    average_rating: float
    sentiment_distribution: dict    # {positive: N, neutral: N, negative: N}
    rating_distribution: dict       # {1: N, 2: N, ..., 5: N}
    language_distribution: dict     # {en: N, zh: N, de: N, ...}
    top_keywords: list[tuple]       # [(keyword, count), ...] Top 20（中英文本地提取）
    unsupported_lang_reviews: int   # 非中英文评论数量（关键词提取交给 LLM）
    review_length_avg: float
    verified_ratio: float
    monthly_trend: list[dict]       # [{month, avg_rating, count}, ...]
```

- **语言检测**：`langdetect` 逐条检测评论语言，加入 `language` 字段
- 星级 → 情感：4-5 星=正面，3 星=中性，1-2 星=负面（语言无关）
- **关键词分语言处理**：
  - 中文 (`zh`)：`jieba` 分词 → 词频 Top 20
  - 英文 (`en`)：空格分词 + 停用词过滤 → 词频 Top 20
  - 其他语种（德/日/俄/西/法等）：本地不提取关键词，标记为 `unsupported_lang_reviews`，在 LLM 报告生成时由模型一并分析
- 无星级（上传数据）：仅做关键词统计，情感留给 LLM

### 2.6 LLM 报告 Agent (`domain/agents/review/review_analyst.py`)

继承 `BaseAgent`（`backend/domain/agents/base.py`），使用 `kimi-k2-thinking-251104` 模型。

**报告结构（Markdown）：**
1. 总体评价摘要（Executive Summary）
2. 情感分布与评分趋势
3. **多语言评论概览**（各语种占比、非中英文评论的关键主题由 LLM 提取）
4. 核心优势（用户喜欢什么，附原文引用）
5. 主要痛点（用户抱怨什么，附原文引用）
6. 功能/维度拆解分析
7. 竞品提及洞察
8. 可执行改进建议
9. 风险预警

**LLM Prompt 要点**：将统计数据（含语言分布）+ 中英文关键词 + 所有评论原文（含非中英文评论）一起传入，指示 LLM 对小语种评论也做关键词和主题提取。

### 2.7 API 端点 (`routers/v2/review_analysis.py`)

```python
router = APIRouter(prefix="/review-analysis", tags=["Review Analysis v2"])
```

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/stream` | SSE 流式（URL 爬取模式） |
| `POST` | `/upload` | SSE 流式（CSV/JSON 上传模式） |
| `GET` | `/status/{session_id}` | 状态查询 |
| `GET` | `/report/{session_id}.html` | HTML 报告 |
| `GET` | `/health` | 健康检查 |

**请求模型：**
```python
class ReviewAnalysisRequest(BaseModel):
    session_id: Optional[str] = None
    url: str = Field(..., description="产品评论页 URL")
    max_pages: int = Field(default=5, ge=1, le=10)
    language_hint: Optional[str] = None   # "en" / "zh" / None(自动)
```

注册路由（修改 `backend/api/routers/v2/__init__.py`）：
```python
from .review_analysis import router as review_analysis_router
router.include_router(review_analysis_router)
```

### 2.8 新增依赖

`backend/requirements.txt` 追加：
```
playwright>=1.40.0
beautifulsoup4>=4.12.0
jieba>=0.42.1
langdetect>=1.0.9
```

`backend/Dockerfile` 追加：
```dockerfile
RUN pip install playwright && playwright install --with-deps chromium
```

---

## 三、数据库

`backend/infrastructure/db/migrations/006_review_analysis.sql`：

```sql
CREATE TABLE public.review_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    url TEXT,
    input_mode TEXT NOT NULL DEFAULT 'url' CHECK (input_mode IN ('url', 'upload')),
    platform TEXT NOT NULL DEFAULT 'unknown',
    product_name TEXT,
    total_reviews_crawled INTEGER DEFAULT 0,
    average_rating DECIMAL(3,2),
    sentiment_distribution JSONB DEFAULT '{}',
    rating_distribution JSONB DEFAULT '{}',
    language_distribution JSONB DEFAULT '{}',
    top_keywords JSONB DEFAULT '[]',
    report TEXT,
    report_html_url TEXT,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending','crawling','analyzing','generating','completed','failed')),
    phase TEXT DEFAULT 'init',
    error_message TEXT,
    raw_reviews JSONB DEFAULT '[]',
    analysis_data JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_review_sessions_status ON public.review_sessions(status);
CREATE INDEX idx_review_sessions_created_at ON public.review_sessions(created_at DESC);
```

---

## 四、前端

### 4.1 新增文件

```
frontend/
  app/components/
    ReviewForm.js              # URL 输入 + 文件上传 + 选项
    ReviewResult.js            # 结果展示（统计卡片 + 图表 + Markdown 报告）
  hooks/
    useReviewStream.js         # SSE hook（复用 useStreamV2.js 模式）
```

### 4.2 修改文件

| 文件 | 修改内容 |
|------|----------|
| `frontend/app/components/ModernSidebar.js` | MENU_ITEMS 新增 `{ key: 'review', icon: MessageSquare, label: '评论分析' }` |
| `frontend/app/page.js` | 新增 `activeView === 'review'` 分支，渲染 ReviewForm + ReviewResult |
| `frontend/lib/constants.js` | 新增 `REVIEW_ANALYSIS_STREAM`, `REVIEW_ANALYSIS_UPLOAD`, `REVIEW_ANALYSIS_STATUS` |

### 4.3 UI 设计

**输入区域（ReviewForm）：**
- Tab 切换：URL 模式 / 上传模式
- URL 模式：URL 输入框 + 平台自动检测标签 + max_pages 滑块(1-10)
- 上传模式：文件拖拽区（.csv/.json）+ 格式说明
- 底部：免责声明 + "开始分析" 按钮

**进度展示：**
- 三阶段进度条：爬取(Page 2/5, 已抓 23 条) → 分析中 → 报告生成中
- 上传模式跳过爬取阶段

**结果展示（ReviewResult）：**
- 顶部统计卡片：平均评分、总评论数、正面/中性/负面占比、语种数量
- 图表区：评分分布柱状图 + 语言分布饼图 + 关键词词频图（Vega-Lite，复用现有 VegaLiteCharts 组件模式）
- 报告区：流式渲染 Markdown（复用现有 react-markdown + remark-gfm）
- 下载按钮：HTML 报告导出

---

## 五、实施顺序

| 步骤 | 内容 | 关键文件 |
|------|------|----------|
| 1 | Schema + 数据库迁移 | `review_schemas.py`, `006_review_analysis.sql` |
| 2 | 爬虫模块（Amazon parser） | `review_crawler.py` |
| 3 | 爬虫模块（AliExpress parser） | `review_crawler.py` 追加 |
| 4 | 统计分析模块 | `review_processor.py` |
| 5 | LLM 报告 Agent | `review_analyst.py` |
| 6 | Graph Engine | `review_engine.py` |
| 7 | API Router（含上传端点） | `review_analysis.py`, `routers/v2/__init__.py` |
| 8 | 前端 UI | `ReviewForm.js`, `ReviewResult.js`, `useReviewStream.js`, sidebar/page/constants 修改 |
| 9 | 集成测试 | Amazon URL + AliExpress URL + CSV 上传 |

---

## 六、验证方式

1. **Parser 单测**：保存 Amazon/AliExpress HTML 快照 → 测试 parse_reviews 输出正确
2. **爬虫集成测试**：真实 URL → 验证爬取结果 + 分页 + 超时处理
3. **上传测试**：准备 CSV/JSON 样本 → POST /upload → 验证跳过爬取直接分析
4. **API 流式测试**：`curl -N -X POST /api/v2/review-analysis/stream` → 观察 SSE 事件序列
5. **前端 E2E**：输入 URL → 观察三阶段进度 → 检查统计卡片/图表/报告渲染
6. **边界场景**：无效 URL、非支持平台 URL、空评论页、爬取超时、大文件上传

---

## 七、关键参考文件（复用现有模式）

| 用途 | 文件 |
|------|------|
| Router SSE 模式 | `backend/api/routers/v2/market_insight.py` (event_generator, EventSourceResponse) |
| Agent 基类 | `backend/domain/agents/base.py` (BaseAgent, get_system_prompt, execute_stream) |
| Graph 引擎模式 | `backend/domain/workflows/market_insight_graph.py` (StateGraph, get_stream_writer, node 结构) |
| Ark LLM 客户端 | `backend/infrastructure/llm/ark_client.py` (create_response_stream_v2) |
| 前端 SSE hook | `frontend/hooks/useStreamV2.js` (fetch + ReadableStream + 事件分发) |
| 前端图表组件 | `frontend/app/components/VegaLiteCharts.js` |
| 侧边栏 | `frontend/app/components/ModernSidebar.js` (MENU_ITEMS) |
| 主页面视图切换 | `frontend/app/page.js` (activeView 分支) |

---

## 八、未来扩展（不在本次范围）

- 更多平台支持（Shopee、eBay、淘宝、京东）
- 定期监控（定时重新爬取同一产品）
- 多产品对比分析
- 与 Market Insight 工作流集成（将评论洞察输入 Social Sentinel Agent）
- 官方 API 替代爬虫（Amazon Product Advertising API 等）
