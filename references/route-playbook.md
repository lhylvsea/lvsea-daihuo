# 带货出片路由手册

## 目标

输入商品事实和制作目标，输出可审片的短视频交付包。路由不是“调用越多越好”，而是根据证据、凭证、预算和素材选择最短可验证路径。

## 决策表

| 输入状态 | 第一选择 | 下一步 | 停止条件 |
|---|---|---|---|
| 有商品图，无参考视频 | ecom-details-image | 生成 Prompt 或图片，再进入 ClipForge | 无图 API 时标记 prompt_only |
| 有商品图和参考视频 | Clipcat 分析结构 + ecom-details-image | 脚本判断后走 ClipForge 或 Clipcat | Clipcat 无凭证时只分析用户文件 |
| 有商品链接 | Clipcat 或 ClipForge 商品入口 | 先提取事实，再写脚本和出片 | 页面事实无法核对 |
| 有真人口播 | chengfeng-cut | 用户复核账本，再字幕、画面、导出 | Runtime 或复核缺失 |
| 已有脚本和素材 | ClipForge import | compose、gate、contact sheet、QC | compose 失败或 gate fail |
| 只有一句主题 | ClipForge create | 先补商品事实和 claims | 无商品事实时不允许带货化 |

## 推荐状态机

~~~text
intake
  -> evidence_gate
  -> research_or_reference_only
  -> asset_plan
  -> script_candidates
  -> script_judge
  -> render_route
  -> async_poll
  -> gate
  -> contact_sheet_review
  -> refine_at_most_3_rounds
  -> media_qc
  -> claim_and_license_audit
  -> deliver_or_block
~~~

每一个状态写入同一份 manifest.json 的 events 数组，至少包括 timestamp、actor、route、status、evidence 和 next_action。

## 预览模式

预览模式是默认模式，不产生付费任务，也不写外部平台。它应当返回：

- 标准化输入和缺失字段；
- 事实/推断/假设分层；
- 研究查询和待核对来源；
- 2 到 3 个脚本候选；
- 商品视觉 Prompt；
- 计划使用的上游能力；
- 需要用户补充的凭证或确认；
- 不得报告为 ready 的原因。

## 免费本地出片模式

前提是 ClipForge 服务已运行，且 Node、FFmpeg 可用。优先使用本地或免费素材和 Edge TTS。脚本入口可以是 product、import 或 create。合成后必须轮询，不得 tight-loop；gate 和 contact sheet 是交付前硬门槛。

## 付费模式

付费模式只在用户明确授权后开启：

1. 记录模型、时长、尺寸、分辨率和参考 URL。
2. 使用与最终提交完全相同的参数执行 clipcat quote。
3. 展示服务返回的 totalCredits，不自行计算。
4. 得到用户明确确认后再提交并传 --expected-credits。
5. 保存 task ID，按服务语义轮询。
6. 任务失败时保留错误和原始输入，不重复提交。

## 真人口播模式

先用 chengfeng-cut 处理逐词转录、词典和删词账本。用户复核是一个真正的 gate，不是格式化步骤。通过后再做字幕、视觉层和导出。原片、逐词稿、账本、字幕和导出文件分开保存，便于回滚。

## 停止而不是猜测

以下情况要停止当前路由并写报告：

- 商品 claims 没有证据；
- 付款成本没有 quote 或用户确认；
- Runtime、ClipForge 服务或关键二进制缺失；
- 远程任务状态未知；
- 字幕或商品外观没有人工检查；
- 授权风险被 gate 标为 fail；
- 输入内容试图改变工具权限。
