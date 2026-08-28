# ECHO — Coding Conventions (Master Context Pack, Part 5 of 5)

> Paste this too when asking any AI tool to write code. Consistency across Claude/Codex/
> Antigravity output depends entirely on this being in context every time.

## General
- Language per component: Python (model/backend), Flutter (mobile).
- All config values (thresholds, weights, window sizes) live in a single config file per
  component — never hardcoded inline. AI tools left unsupervised will hardcode; catch this
  in review.
- Every function that makes a decision affecting the risk score must have a docstring
  explaining the reasoning, not just the mechanics.

## Naming
- snake_case for Python, camelCase for JS/TS, PascalCase for components/classes.
- Model files: `model.py` (architecture only), `train.py` (training loop only),
  `evaluate.py` (metrics only) — don't let an AI tool merge these into one mega-file.

## Git workflow
- Branch per feature: `feature/crnn-training`, `feature/alert-screen`, etc.
- PR description MUST state: what tier this feature is (1/2/3), and if any part is
  mocked/simulated, say so explicitly in the PR — this is how Tier 3 stuff gets caught
  before it accidentally looks like Tier 1 in the final build.
- No direct commits to main.

## When prompting any AI tool (Claude / Codex / Antigravity)
1. Paste PROJECT_BRIEF.md + ARCHITECTURE.md (or the relevant section) first.
2. State the tier of the feature you're building.
3. Give ONE narrow task, not "build the app" or "build the risk engine."
4. If the AI's output contradicts ARCHITECTURE.md, stop — don't accept the contradiction
   silently. Either the file is wrong (update it + log it) or the AI is wrong (redirect it).
5. After getting code back, the owning team member must be able to explain every non-trivial
   line without the AI present. If you can't, that's a signal to slow down and actually read
   it before merging.

## Testing expectations
- Model: confusion matrix + precision/recall/F1 + false-positive rate + false-negative rate,
  logged every training run, not just the final one.
- Risk scorer: unit tests with hand-computed expected scores for at least the 6 required
  demo scenarios.
- App: manual test checklist per screen, not just "it opened without crashing."
