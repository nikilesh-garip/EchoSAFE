# ECHO — Project Brief (Master Context Pack, Part 1 of 5)

> PASTE THIS ENTIRE FILE AT THE START OF EVERY AI SESSION (Claude, ChatGPT/Codex, Antigravity)
> BEFORE giving any task. This is the ground truth. If an AI tool suggests something that
> contradicts this file, the file wins — flag the conflict in DECISIONS_LOG.md, don't silently
> let the tool improvise.

## What Echo Is

Echo is a mobile safety app that listens to environmental audio, uses an AI model to detect
hazardous sounds (gunshot, explosion, distress scream, glass breaking, fire alarm, siren,
aggressive shouting, crash/impact), estimates a risk score using context signals (to avoid
false alarms from movies/TV/games), and provides emergency guidance + nearby police/hospital
locations. It includes a Demo Mode for panel evaluation.

## Team

- 3 people. See TEAM_ROLES.md for who owns what.
- 1–2 month timeline.
- Compute: Kaggle (30 GPU hrs/week) + Colab (free T4) for training. Intel Ultra 5 226V laptop
  w/ Arc 130V iGPU (8GB) for local dev + OpenVINO inference benchmarking. No CUDA locally.

## The Non-Negotiable Rule: Tiered Honesty

Every feature belongs to exactly one tier. This is not optional and not up for re-negotiation
mid-project without updating TIER_TABLE.md and telling the whole team.

- **Tier 1 — Real, working, must demo live.**
- **Tier 2 — Real but simplified implementation (same output, lighter internals).**
- **Tier 3 — Simulated/scripted for Demo Mode, explicitly labeled as such in the report.**

Full breakdown in TIER_TABLE.md. Do not let an AI tool "upgrade" a Tier 3 item into something
it implies is real — this misrepresents the project and will fall apart under panel questioning.

## Core Pipeline (Tier 1 — must work end-to-end)

Microphone → rolling audio buffer (2-5s) → YAMNet transfer-learning classifier (two-pass:
fast/short pass, then re-inference on longer window as "verification") →
heuristic context/risk scorer → risk level (NORMAL/SUSPICIOUS/POSSIBLE DANGER/HIGH-RISK) →
rule-based guidance lookup → map/nearby-places display → alert screen with action buttons.
(See DECISIONS_LOG.md entry #8: this replaced an earlier from-scratch CNN-Transformer.)

## What We Deliberately Cut From the Original Spec (and why)

- No true 24/7 background OS-level monitoring — session-based (app open/foreground service)
  monitoring instead. See DECISIONS_LOG.md entry #1.
- No AST/PANNs/BEATs/CLAP as a second model — same YAMNet-based classifier run twice at
  different window sizes/thresholds simulates "two-stage verification." Entry #2 (superseded
  by entry #8, which replaced the from-scratch classifier itself with a fine-tuned YAMNet head
  — the "no second heavy model" reasoning still holds).
- No full ASR (Whisper) — small constrained keyword-spotter for ~6 target phrases only. Entry #3.
- No real nearby-device networking — Tier 3, scripted responses in Demo Mode only. Entry #4.
- No pruning/QAT — post-training dynamic-range quantization (TFLite) + OpenVINO IR export
  for laptop-side benchmarking only. Entry #5.
- No movie-theatre geofencing or crowd-scatter detection layers — rejected as unreliable/
  out of scope for a mini-project (see earlier chat reasoning; not re-litigated).
- No laptop/desktop full feature parity — mobile is the target platform. Laptop is used for
  training, dev, and OpenVINO benchmarking only, not as a second shipped app.

## Target Hazard Classes (v1)

Gunshot, Explosion, Distress scream, Glass breaking, Fire/smoke alarm, Siren
(police/ambulance merged as one class unless dataset supports split), Aggressive shouting,
Normal/background (negative class).

## Required Demo Tests (must all work live, per TIER_TABLE.md Tier 1)

1. Gunshot audio → high risk + guidance + nearby police/hospital
2. Distress scream → risk assessment + guidance
3. Glass breaking → context/risk evaluation
4. Normal conversation → NORMAL / no hazard
5. Movie w/ gunshots (media-playback context active) → reduced/uncertain risk
6. Gunshot + scream + shouting sequence → very high risk, immediate guidance

## Datasets

UrbanSound8K + ESC-50 (documented in DATASET_TABLE.md) + a self-recorded smartphone-mic
test set (~10 min per team member, playback of clips through a speaker) for domain-mismatch
evaluation. No AudioSet (broken/YouTube-ID licensing issues).

## Non-negotiable Engineering Rule

Never let an AI tool fake functionality without labeling it. If a tool builds something that
only works with hardcoded/mocked data, that MUST be flagged Tier 3 in the same PR description.
Silent faking is the #1 way this project falls apart at evaluation.
