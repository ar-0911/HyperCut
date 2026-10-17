# 0009: Build in parallel with braid

Status: accepted, 2026-10-17

**Decision.** After the skeleton (plan schema, Claude helper, layout) is on `main`, the stages are built by
parallel agents with [braid](https://github.com/ar-0911/braid) (`braid do --base feature/mvp`), landing on
`feature/mvp`, which then goes to `main` as one pull request.

**Why.** The stages only meet at the edit plan, so they can be built at the same time without editing each
other's files. braid gives each agent its own branch, predicts conflicts early, reviews and tests before
landing.

**Consequences.** `CLAUDE.md` lists which module each stage owns, so the planner can assign file ownership.
Nothing lands on `feature/mvp` unless `pytest` passes.
