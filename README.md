# 📈 WeaveAI 智能分析助手 (Pro Version)

**告别感觉，让数据与AI为您引航。**

---

## 📖 项目简介 (Project Overview)

**WeaveAI** 是一个专为跨境电商卖家设计的、集成化的智能决策平台。本项目采用现代Web技术栈，实现了**前后端分离**架构，提供了一个从“**机会洞察 -> 自我验证 -> 行动方案**”的完整商业分析闭环。

*   **后端**: 使用 **FastAPI** 构建，提供高性能的API接口，负责所有AI调用和重度数据分析。
*   **前端**: 使用 **Next.js (React)** 和 **Tailwind CSS** 构建，提供了一个美观、流畅、响应式的用户界面。

## ✨ 核心功能 (Key Features)

*   **命令面板式交互**: 通过弹出式模态框引导用户创建“战略档案”。
*   **全屏沉浸式仪表盘**: 采用“固定侧边栏 + 宽主内容区”的专业布局。
*   **自由工作流**: 用户可在“机会洞察”和“自我验证”模块间自由切换。
*   **流式AI响应**: 所有AI生成的内容（市场报告、评论分析、行动计划）都以流式输出，提供卓越的实时交互体验。
*   **数据驱动分析**: 集成了LSTM销售预测、K-Means热销品聚类、Vader情感分析等多种数据模型。

## 🛠️ 技术栈 (Technology Stack)

### 后端 (Backend)
*   **框架**: `FastAPI`
*   **服务器**: `Uvicorn`
*   **AI/ML**: `volcenginesdkarkruntime`, `TensorFlow (Keras)`, `Scikit-learn`, `vaderSentiment`
*   **数据处理**: `Pandas`, `Numpy`

### 前端 (Frontend)
*   **框架**: `Next.js (App Router)`, `React`
*   **UI**: `Tailwind CSS`
*   **组件**: `ReactMarkdown`, `rc-slider`, `react-plotly.js`

## 🚀 快速开始 (Getting Started)

### 1. 启动后端服务

```bash
# 进入后端目录
cd backend

# (如果首次运行) 创建并激活虚拟环境 (推荐Python 3.10)
python3.10 -m venv venv
source venv/bin/activate  # macOS/Linux
# .\venv\Scripts\activate  # Windows

# (如果首次运行) 安装Python依赖
pip install -r requirements.txt

# 确保在 backend 目录下有一个 .env 文件，并包含 ARK_API_KEY

# 启动后端开发服务器
uvicorn main:app --reload
```

### 2. 启动前端服务

```bash
# (在另一个终端中) 进入前端目录
cd frontend

# (如果首次运行) 安装Node.js依赖
npm install

# 启动前端开发服务器
npm run dev