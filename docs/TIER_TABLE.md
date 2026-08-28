# ECHO — Tier Table (Master Context Pack, Part 4 of 5)

> This table is the honesty contract. It goes in the final report near the front, unedited.
> Every feature from the original master spec is mapped here. If an AI tool builds something
> not on this list, add it here before merging — don't let scope grow silently.

| # | Feature | Tier | Notes |
|---|---------|------|-------|
| 1 | Hazardous sound classification (YAMNet transfer-learning head) | 1 | Real locally; real-world performance claims require the readiness gates to pass |
| 2 | Two-pass verification (same model, two windows) | 1 | Real; replaces separate 2nd model |
| 3 | Heuristic context/risk scorer | 1 | Real; documented weighted formula |
| 4 | Temporal event sequence analysis | 1 | Real; short rolling event history window |
| 5 | Rule-based emergency guidance | 1 | Real; static lookup table per hazard type |
| 6 | Maps/nearby police-hospital lookup | 1 | Real; Places API or OSM Overpass |
| 7 | Demo Mode (8-class WAV injection + live mic, covers the 6 required scenarios) | 1 | Real; runs the actual /detect pipeline on real or labeled-synthetic clips, must work live for panel. Implemented in the browser dashboard (`backend/static/`); the Flutter app's Demo tab mirrors the same real pipeline call. |
| 8 | Alert screen, History, Contacts, Settings UI | 1 | Real |
| 9 | Session-based (foreground) mic monitoring | 1 | Real, scoped down from 24/7 background |
| 10 | Keyword spotting (6 fixed phrases) | 2 | Real but simplified vs full ASR; cut first if behind |
| 11 | TFLite quantized export (mobile) | 2 | Real, post-training quantization only |
| 12 | OpenVINO export + iGPU benchmarking | 2 | Real, differentiator; simplified vs pruning/QAT |
| 13 | Nearby-device corroboration alerts | 3 | Simulated/scripted only, disclosed in report |
| 14 | Cloud-scale verification model (AST/PANNs/CLAP) | Cut | Rejected — see Decisions Log #2 |
| 15 | Full 24/7 OS-level background monitoring | Cut | Rejected — see Decisions Log #1 |
| 16 | Full ASR (Whisper-scale) | Cut | Rejected — see Decisions Log #3 |
| 17 | Movie-theatre geofencing | Cut | Rejected earlier — unreliable POI/GPS indoors |
| 18 | Crowd-scatter detection via nearby users | Cut | Rejected earlier — research-grade problem, unsolvable at this scope |
| 19 | Laptop/desktop full app parity | Cut | Mobile is the shipped platform; laptop is dev/training only |

**Rule:** anything marked Cut stays in the report as "Future Work," explained honestly —
this is what turns a scope cut into a strength during Q&A, not a weakness.
