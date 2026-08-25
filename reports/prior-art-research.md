# Prior-art research

Date: 2026-08-25

## Scope

Reviewed the user-provided X post and the public repositories for the four named capabilities. The X page itself may be unavailable to a non-authenticated client, so the wording of the post was cross-checked against the public repository names and the article's four labels, not treated as a complete technical specification.

## Sources reviewed

- X post: https://x.com/mnmn94253156337/status/2092053217869955429
- https://github.com/liangdabiao/ecom-details-image
- https://github.com/xixihhhh/clipforge
- https://github.com/clipcat-ai/clipcat-skill
- https://github.com/Ceeon/videocut-skills
- https://github.com/lhylvsea/lvsea-zao-skill

## Findings

- ecom-details-image is prompt-first and can optionally call a user-configured OpenAI-compatible image API.
- ClipForge requires a running local service and has hard delivery rules around async compose, gate and contact sheet review.
- Clipcat provides research and video commands, but paid video generation requires a server quote and explicit confirmation.
- Ceeon's videocut-skills repository is a Codex Marketplace bootstrap with multiple chengfeng-* sub Skills and a separate Runtime.
- The composite must preserve provider and human evidence boundaries. Installing a Skill or passing CLI help is not evidence of a real video.

## Keep / adapt / reject / invent

See references/source-map.md. The composite keeps the operational boundaries, adapts the route into one Chinese-first entrypoint, rejects unreviewed remote installers and automatic publishing, and invents the shared claims gate, artifact manifest and cross-provider degradation states.
