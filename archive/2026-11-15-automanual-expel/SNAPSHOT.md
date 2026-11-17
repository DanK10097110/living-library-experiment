# Snapshot: AutoManual + ExpeL rule manual (2026-11-15)

The full code, tests, tools and configs saved before switching the E library to MACLA. 75 tests pass.

What this version is:
- Library for E/E-minus: a rule manual (`living_library/manual.py`), AutoManual-style rules (types,
  case-conditioned Builder after every practice game, one Success Process per task type) managed
  ExpeL-style (importance 2, upvote/edit +1, downvote -1, removed at 0), no cap, the 8 most
  relevant rules shown per game. Code skills (Voyager-style refinement loop) still run alongside.
- Model: Qwen3.5-9B Q4_K_M, 24 slots, -ub 4096; practice batches of 8.

Measured on real data (offline Builder over 40 archived practice games, then 30 development games,
frozen manual vs condition C on the same games): capped manual 23/30, uncapped 21/30, C 19/30.
Built manuals: /root/ll-runs/manual-offline.json and manual-offline-v2.json (WSL).
The ExpeL vote version was unit-tested but not yet run on real games.

To restore: copy living_library/, tests/, tools/, configs/, pyproject.toml back over the repo.
