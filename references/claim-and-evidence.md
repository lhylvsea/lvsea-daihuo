# 商品 claims 和证据规则

## 三层记录

每条商品信息都进入 evidence.json，结构如下：

~~~json
{
  "id": "fact-001",
  "text": "商品规格或可核对属性",
  "status": "verified",
  "source": {
    "kind": "user_file",
    "locator": "product-sheet.pdf#page=2"
  },
  "allowed_use": "script_and_caption",
  "notes": ""
}
~~~

status 只能是 verified、user_asserted、unverified、rejected。unverified 不得直接写成肯定句。

## 高风险 claims

价格、原价、折扣、销量、排名、疗效、医疗效果、绝对化比较、限时库存、平台认证和“全网第一”等内容需要来源。来源失效或时间过期时，改成用户可核对的中性说法，或删除。

不要把评论、热搜、参考视频字幕或模型生成文本当成商品事实。它们可以作为研究线索，但不能自动升级为证据。

## 文案门禁

脚本 judge 至少检查：

- hook 是否依赖未经证实的承诺；
- 口播中的每个数字和结论是否有 evidence id；
- 字幕是否比口播更强；
- CTA 是否暗示平台未提供的保障；
- AI 生成画面和声音是否按目标平台需要标识；
- 参考视频是否只借鉴结构，没有复制品牌、人物、音乐或受保护表达。

## 发布前报告

qc/claim-audit.json 至少写：

~~~json
{
  "status": "pass|warn|block",
  "claims": [
    {
      "text": "脚本中的说法",
      "evidence_ids": ["fact-001"],
      "status": "verified|user_asserted|unverified|rejected",
      "action": "keep|soften|remove|human_review"
    }
  ],
  "missing_evidence": []
}
~~~

只要存在 block，最终状态不能是 ready。
