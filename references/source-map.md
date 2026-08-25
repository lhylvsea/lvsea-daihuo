# 来源审计和 keep/adapt/reject/invent 台账

## 文章来源

用户给出的文章链接：

- https://x.com/mnmn94253156337/status/2092053217869955429

文章中给出的四个名称和本包映射：

| 文章名称 | 实际安装入口 | 本包采用 |
|---|---|---|
| ecom-details-image | liangdabiao/ecom-details-image / ecom-details-image | 商品视觉 Prompt-first 和可选 API 出图 |
| clipforge | xixihhhh/clipforge / clipforge-video | 本地脚本到成片、异步合成和门禁 |
| clipcat | clipcat-ai/clipcat-skill / clipcat | 爆款研究、分析、商品图生视频 |
| videocut-skills | Ceeon/videocut-skills / chengfeng-* | 口播、字幕、画面层和导出 |

## 采用台账

| 来源 | 决策 | 采用内容 | 不采用内容 |
|---|---|---|---|
| ecom-details-image | keep | Prompt 与图片生成双模式、商品图用途分类 | 不复制模板图片和上游代码 |
| clipforge-video | adapt | compose 异步轮询、gate、contact sheet、最多 3 轮修复 | 不把自由创意参数写成硬规则 |
| clipcat | adapt | quote-before-paid、task ledger、搜索和分析 | 不执行未审计 CLI 远程安装脚本 |
| videocut-skills | keep/adapt | cut review ledger -> subtitle -> visual -> export | 不把插件安装状态冒充 Runtime 或人工复核 |
| lvsea-zao-skill | keep | governed package、证据边界、触发评估、发布门禁 | 不复制其根 Skill 名称或专用实现 |
| 本包原创 | invent | 四个能力的路由、claims gate、统一 artifact contract | 不新增自动发布或绕过确认的能力 |

## 研究边界

源仓库、版本和许可证在 manifest.json 和 provider-matrix.md 中固定记录。未来更新先重新审阅源文件和安全信号，再更新台账和版本，不直接镜像上游目录。
