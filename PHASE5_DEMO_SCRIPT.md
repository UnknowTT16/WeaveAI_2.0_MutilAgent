# Phase 5 Demo Script（3~5 分钟）

## 1. 演示目标

- 在 3~5 分钟内让评委感知三件事：
  1) 系统可以稳定跑通多 Agent 协作；
  2) 关键结论可追溯；
  3) 结果可一键导出为可复用路演包。

## 2. 演示前 5 分钟检查清单

- 后端健康：`http://127.0.0.1:8000/health` 返回 `healthy`。
- 前端打开：`http://localhost:3000`。
- 评委模式卡片可见（60 秒极速 / 3 分钟标准 / 深度演示）。
- 下载按钮可用（导出路演包 zip）。
- 备用命令窗口已打开（PowerShell）。

## 3. 标准演示流程（推荐：3 分钟标准）

### 0:00 ~ 0:30 开场（价值锚点）

话术建议：

> 我们不是只生成一段答案，而是用 Supervisor-Worker + 多 Agent 辩论，
> 把“是否可执行、是否可追溯、现场是否稳定”同时解决。

### 0:30 ~ 1:30 启动分析（评委模式）

- 点击 `3 分钟标准` 卡片的 `一键运行`。
- 强调：该模式默认 1 轮辩论，平衡速度与可信度。

话术建议：

> 这里可以看到多 Agent 并行采集，然后进入辩论剧场形成共识，
> 不是单点模型一次性输出。

### 1:30 ~ 2:30 解释过程与稳定性

- 在 `执行进度` 展示 4 个市场 Agent 的状态。
- 在 `辩论剧场` 展示 challenge/response 的过程。
- 在 `演示保护模式` 说明弱网断流时 90 秒自动回补机制。

话术建议：

> 即使现场网络抖动，系统会进入保护模式自动回补状态，
> 确保演示不中断、不重跑。

### 2:30 ~ 3:30 展示结果与证据

- 在 `关键指标看板` 展示：全程耗时、稳定性评分、证据覆盖率、降级次数。
- 在 `综合洞察报告` 快速定位 1~2 条可执行结论。

话术建议：

> 这里的证据覆盖率是可追溯能力的量化指标，不是主观打分。

### 3:30 ~ 4:30 一键导出路演包

- 点击顶部下载按钮，下载 zip。
- 展示 zip 内容：`report.html`、`executive_summary.md`、`evidence_pack.json`、`demo_metrics.json` 等。

话术建议：

> 我们交付的不只是页面，而是可归档、可复审、可复用的标准化资产包。

## 4. 备用演示路径（网络或模型波动时）

- 优先切换到 `60 秒极速` 模式。
- 若前端异常，使用备用命令生成并导出：

```powershell
# 运行位置：PowerShell，项目根目录
$sid=[guid]::NewGuid().ToString()
$body=@{
  session_id=$sid
  profile=@{
    target_market="Germany"
    supply_chain="Consumer Electronics"
    seller_type="brand"
    min_price=30
    max_price=90
  }
  debate_rounds=0
  enable_followup=$false
  enable_websearch=$false
  retry_max_attempts=1
  retry_backoff_ms=100
  degrade_mode="partial"
} | ConvertTo-Json -Depth 6 -Compress

C:\Windows\System32\curl.exe -s -H "Content-Type: application/json" -X POST "http://127.0.0.1:8000/api/v2/market-insight/generate" -d $body > $null
C:\Windows\System32\curl.exe -s "http://127.0.0.1:8000/api/v2/market-insight/status/$sid"
C:\Windows\System32\curl.exe -L -o "weaveai-roadshow-$sid.zip" "http://127.0.0.1:8000/api/v2/market-insight/export/$sid.zip"
```

## 5. 演示收尾（10 秒）

话术建议：

> 这套系统的核心不是“写得多快”，而是“在不确定现场里，持续产出可追溯、可导出的高质量决策材料”。
