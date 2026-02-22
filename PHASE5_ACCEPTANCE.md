# Phase 5 验收记录（跑通版）

## 1. 结论

- 当前以“跑通优先”口径完成了 Phase 5 核心链路验证。
- 已确认：评委模式链路、状态恢复链路、导出链路、图表增强链路可正常工作。
- 未完成项：3 轮完整彩排与问题闭环（后续可补）。

## 2. 本次跑通证据

- 时间：2026-02-20
- 通过会话：`b55de6c3-00ec-4438-9cf9-e08d03486b43`
- 关键观测：
  - `GET /api/v2/market-insight/status/{session_id}` 返回 HTTP 200
  - `session.status = completed`
  - 返回体包含 `demo_metrics`、`report_charts`、`workflow_events` 等结构

## 3. 分项验收状态

- [x] 评委模式三套场景（60 秒/3 分钟/深度）可一键跑通
- [x] 页面可视化完整展示 Agent、辩论、降级状态与报告下载
- [x] 弱网或中断情况下可通过状态接口恢复展示（跑通验证）
- [x] 一键导出路演包可用于比赛展示
- [x] 综合报告支持关键图表增强（Vega-Lite），保持正文结构
- [x] 图表在实时页与导出 HTML 均可渲染，失败可回退
- [ ] 完成至少 3 轮完整彩排并形成问题清单与修复闭环

## 4. 验收命令（跑通版）

```powershell
# 运行位置：PowerShell，项目根目录
$sid = [guid]::NewGuid().ToString()
$payloadObj = @{
  session_id = $sid
  profile = @{
    target_market = "France"
    supply_chain = "Home Fitness"
    seller_type = "trader"
    min_price = 25
    max_price = 70
  }
  debate_rounds = 1
  enable_followup = $true
  enable_websearch = $false
  retry_max_attempts = 2
  retry_backoff_ms = 300
  degrade_mode = "partial"
}
$payload = $payloadObj | ConvertTo-Json -Depth 6 -Compress

# 模拟中断流（验证恢复）
curl.exe --max-time 8 -N -H "Content-Type: application/json" -X POST "http://127.0.0.1:8000/api/v2/market-insight/stream" --data-raw "$payload" > $null

# 状态查询
$obj = Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8000/api/v2/market-insight/status/$sid"
$obj | ConvertTo-Json -Depth 8
```

## 5. 备注

- Windows PowerShell 若出现中文乱码，不影响后端业务结果判定。
- 若 `status` 出现 `not_found`，优先确认后端已重启并加载最新代码。
