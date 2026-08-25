# Creation handoff

## Intent

Create one public, reusable, Chinese-first Skill named lvsea-daihuo that turns the four article capabilities into a runnable, auditable production route.

## Confirmed constraints

- Owner: 海洋哥 / lhylvsea.
- Name: lvsea-daihuo.
- Default behavior: preview and no publication.
- Paid provider use requires quote and explicit confirmation.
- Public package must not contain secrets, private media or machine-specific paths.
- Upstream source is referenced, not copied wholesale.

## Package decisions

- One discoverable root SKILL.md.
- Long operational details are on-demand references.
- Deterministic route and contract checks live in scripts.
- Positive, negative, near-neighbor and adversarial trigger cases live in evals.
- Runtime/provider and human-review gaps are represented as missing_evidence.
- Composite license is MIT; upstream licenses remain applicable to their own source and services.

## Acceptance gates

- package structure and root entrypoint pass.
- trigger fixture passes all cases.
- Skill IR and context budget are generated.
- local unit tests and secret scan pass.
- GitHub PR/release/clean install pass before public completion.
- provider-backed output remains missing evidence until a real run and human review exist.
