# ECHO — Team Roles & AI Tool Assignment

| Person | Owns | Primary AI tool | When to use which |
|--------|------|------------------|--------------------|
| A (you) | YAMNet transfer-learning model, training, evaluation, TFLite + OpenVINO export | Claude (reasoning/architecture) + Kaggle/Colab notebooks | Use Claude for "why this architecture," "explain this paper's method," writing evaluate.py logic. Use Codex only for boilerplate (data loaders, plotting confusion matrices) after the architecture itself is decided by you, not the AI. |
| B | Mobile app (all screens), maps integration | ChatGPT/Codex (agentic coding) | Give Codex one screen at a time with the ARCHITECTURE.md screen list. Antigravity/Gemini as second option specifically for Places/Maps API work. |
| C | Risk scorer, guidance rule-base, backend, Demo Mode, integration/testing | ChatGPT/Codex + Antigravity | Codex for FastAPI boilerplate; write the risk_scorer.py weights/logic yourself (or with Claude) since you need to defend this formula in the viva too. |

## Daily sync (15 min, async ok — post in shared chat)
1. What I built today (file names, not vague descriptions)
2. Any new/changed decision → goes in DECISIONS_LOG.md same day
3. Any blocker

## Weekly sync (30 min, live)
- Merge status across the 3 workstreams
- Re-check against TIER_TABLE.md — has anything silently upgraded from Tier 3 to looking
  like Tier 1? Catch this weekly, not at week 7.
- Re-confirm: can each person explain their own code without the AI tool open?
