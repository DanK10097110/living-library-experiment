# Handoff: living-library experiment (updated 2026-11-19 evening)

Work autonomously; never stop to wait for the owner when they are away. Commits are allowed (plain messages,
no Claude/AI mention, no Co-Authored-By); push only when the owner asks. All code changes go through
subagents; the architect designs, reviews and inspects libraries. Record every library design decision with
its reason in `results/DECISIONS.md`; run events in `results/LOG.md` (timestamped).

## State at close (2026-11-19 ~20:30)
- The study (`/root/ll-runs/study`, WSL) is PAUSED; the model server is stopped. No runs are going.
- Done and kept: C evaluation (134 OOD + 70 ID), gate-C, D practice 112/300, E-minus practice 112/300.
- E practice (104 games) must be redone: E lost to E-minus on the same games (47 vs 61 of 94), traced to
  recipe drift (see DECISIONS 2026-11-19). That is fixed (commits b409d01, 77a9081; 198 tests pass).
- The E-minus probe passes against the study (`results/probes/e-minus-51a3f2752a063127.json`), so restarting
  only E keeps C, D and E-minus.

## Next steps
1. Resume with only E rebuilt: `tools\run.ps1 study -RestartE -MaxHours 12 -Workers 24`
   (run.ps1 starts the server if it is not running; check no `STOP` file is in /root/ll-runs/study).
   E replays from game 0, and the 75-game gate runs again (stops there if E < C; then inspect, `-PastGate`).
2. Watch E vs E-minus paired on the same practice games (same order and seeds in every condition):
   `%TEMP%`-free check = compare `record.success` per position in checkpoints/practice-E-0 vs practice-E-minus-0.
   E should now be >= E-minus. Also check that recipe texts stay stable and that the "instructed command always
   rejected" retirements fire only on truly impossible steps (e.g. "take the lamp").
3. After practice: E evaluation (part of the study), then the 3-point library comparison the owner asked for:
   `python tools/snapshot_eval.py /root/ll-runs/study --at 100 --output /root/ll-runs/snap-eval-100` and `--at 200`
   (~3 h each, run after the study), then `python tools/compare_snapshots.py /root/ll-runs/study
   /root/ll-runs/snap-eval-100 /root/ll-runs/snap-eval-200` -> `results/library/SNAPSHOT-EVAL.md`.
4. Keep library snapshots every 25 games (tracking only): `python tools/library_snapshots.py /root/ll-runs/study`
   -> `results/library/snapshots/`, `trends-*.csv`, `TRENDS.md`; refresh `results/library/current-*.{json,txt}`.

## Monitoring routine (every ~30 min while running)
- `tools\run.ps1 status`; checkpoint counts per stream; `nvidia-smi` (average GPU >= 90% is the target;
  idle server slots are fine); VRAM: llama-server ~9.6 GB dedicated + ~1.1 GB pinned host ("shared") is normal,
  spill would show as shared growing well above that.
- RAM: keep >= ~8 GB free. At most ~3 concurrent experiment processes (each worker loads the embedder).
  When free RAM drops, drop the WSL page cache: `wsl -u root -- bash -c "sync; echo 3 > /proc/sys/vm/drop_caches"`.
- Library: `python tools/show_library.py /root/ll-runs/study [--stream practice-E-minus-0]`; read the rules.
- Nightly: scheduled task `LivingLibrary-NightlySleep` stops llama-server and sleeps the PC at 00:00
  (`tools/nightly-sleep.ps1`); save state before, resume after waking (runs resume from checkpoints).

## Known, accepted
- Shared two-object subgoal check can pass with only the first object placed (skipped test in
  tests/test_e_management.py). Not fixed: equal for all conditions; fixing would invalidate C/D games.
- Practice batches log a retirement once per game of the batch (cosmetic).
- Retrieval: flat task-keyed retrieval is kept for long runs (results/lab/REPORT.md); tree idea dropped.

## Environment
- WSL Ubuntu-24.04 as root, venv `/root/venvs/living`; runs in `/root/ll-runs`. Tests:
  `wsl.exe -d Ubuntu-24.04 -u root -- bash -lc "cd '/mnt/c/Git Repos/living-library-experiment' && /root/venvs/living/bin/python -m unittest discover -s tests"`.
- Model: Qwen3.5-9B Q4_K_M, `tools/serve-model.ps1` (port 8000, 24 slots). Git Bash -> WSL: prefix
  `MSYS_NO_PATHCONV=1` so /mnt paths are not rewritten.
- Rules: no `find`/recursive scans over drives; `lc` only for large jobs; never print the VM password.
- Presentation examples: `examples/` (pushed to origin 2026-11-19).
