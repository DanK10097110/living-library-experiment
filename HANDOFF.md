# Handoff: living-library experiment (written 2026-11-18)

The owner is away for a while. Work autonomously: never ask questions, never wait for approval.
Keep the GPU busy with useful episodes, check often that everything is going well, fix problems
(through subagents) and continue. Do not commit or push. Save progress often, especially the library.

## Goal and order of work
The goal is FIRST a good library + retrieval + management process, verified on cheap checks,
and only THEN the long experiments. Don't spend long-run compute on a library you haven't inspected.
1. Finish the work that was cut off (section "Unfinished work").
2. Iterate on the library with the 48-game practice + 30-game check (`tools/when-idle-check.ps1`).
   Read every rule of every new library yourself and judge it: is it general, short, factually right
   for ALFWorld, useful? Look at win/loss per rule, hidden notes, retirements, avoid-rules, retries.
3. When the library is good (rules correct and general, E clearly >= C on the check, nothing odd in
   the report), run the study: `tools\run.ps1 study -RestartLibrary -MaxHours 12` (keeps C/D games).
   It stops at the 75-game gate (exit code 3) unless E >= C; then inspect `gate.json` and the library
   (`/root/ll-runs/study/checkpoints/practice-E-0/`, last file's `memory.rules`). Continue with
   `-PastGate` only if the library looks right; otherwise fix, then `-RestartLibrary`.
4. Keep checking during long runs too: some problems (wrong rules, retrieval noise, stalls) only show
   up later, not in the quick checks.

## Periodic review (every ~30-60 min while runs are going; use ScheduleWakeup/Monitor, not polling loops)
- Progress: `tools\run.ps1 status`, the run log, checkpoint counts per stream; are games advancing?
- GPU: `nvidia-smi` (utilization should be high during runs; idle GPU with a pending run = problem).
- Library: print the current rules (script: see "Useful commands"); look for wrong, duplicate, vague,
  instance-specific rules, rules with bad W/L still visible, hidden notes leaking, retrieval showing
  irrelevant rules. Copy a snapshot of rules + a short note to `results/<run>-<time>/` each review.
- Errors: Builder errors/rejections in reports, exceptions in logs, model server health
  (`http://127.0.0.1:8000/health`).
- If something is wrong: stop the affected run, have a subagent fix it (with tests), rerun the cheap
  check, then continue. Write what you found and did to `results/LOG.md` (append, timestamped).

## Implementation rule
All code changes are made by subagents (general-purpose or `model: "sonnet"`); you design, brief,
review results and inspect libraries. Briefs must say: tests in WSL must pass, C/D probe test must
keep passing, no commits, no `find` over drives, never print passwords.

## Nightly sleep (set this up first, via a subagent)
- The lc idle watcher must stay on at all times (`lc watch status`; README "Idle watcher" in
  `C:\Users\DaGuest\local-coder`). lc files: claim on the lc workboard before editing, release after.
- At 23:59 every day the agent must get a message that the PC and GPU go to sleep in one minute.
  Suggested: a CronCreate job in this session at 23:59 whose prompt is "PC sleeps at 00:00: save
  state now (copy current library + notes to results/, note what is running in results/LOG.md)".
  Runs are checkpointed per game and resume, so nothing else is needed.
- At 00:00 the PC goes to sleep: a per-user Windows scheduled task (no admin) that stops
  llama-server and suspends the PC (reuse lc's sleep code in `bin/power.mjs` if it has one;
  otherwise PowerShell `Add-Type -AssemblyName System.Windows.Forms;
  [System.Windows.Forms.Application]::SetSuspendState('Suspend', $false, $false)`). Test that the task
  is registered (`schtasks /query`), not by sleeping the PC.
- After waking, restart whatever was running (resume from checkpoints).

## Unfinished work (do first)
1. Avoid-rule ("Anti-Pattern") live check: built in `living_library/avoid.py`, passes synthetic
   check `tools/avoid_rule_check.py` (60/60). The real run was stopped before results. Run
   `tools\when-idle-check.ps1`, copy `/root/ll-runs/mini-macla/{rules.json,report.txt}` to
   `results/mini-macla-avoid-rules/`, judge the avoid-rules (specific? useless? wrong?).
   Known: real failure pools rarely share a pattern; some wordings are tautological.
2. Retrieval comparison on FROZEN rules (`results/mini-macla-retrieval/rules.json`, the best library
   so far: manual 24/30 vs C 19/30). Implement as a switchable option (no change to rule writing):
   current (task-keyed: similarity to tasks where the rule won, fallback rule text), goal with
   object/receptacle names replaced by placeholders, planner-plan (HyDE: the planner's subgoal
   descriptions vs plans of games where the rule won), plan + steps (re-select actor rules per
   subgoal using current subgoal + recent actions; credit all rules shown in the game). Run the same
   30 games per variant with the same frozen rules (`tools/manual_check.py <rules.json>
   /root/ll-runs/old-pilot-9b-v1 --games 30` style), compare wins, paired wins/losses, rules shown.
   Note: the embedder matches mostly on the object ("heat apple" ~ "clean apple" 0.97 vs
   "heat egg" 0.81), which is why other task types' rules are only borrowed when none exist.
3. Known library weaknesses: heat tasks never won (model does not find the microwave route);
   look-at-in-light recipe slightly wrong (take the object to the desklamp, then use it);
   two weak heat rules still visible.

## What exists (all uncommitted on main; tests: 131 pass)
- Rule manual `living_library/manual.py`: AutoManual types + ExpeL votes + MACLA (Beta reliability,
  expected utility, contrastive refinement, merge, prune); rules <= ~25 words, no numbered entities;
  ExpeL-style retries of lost practice games (`manual.RETRIES = 3`, first attempt scored, retry cost
  counted); rules from never-won games are hidden Builder notes until confirmed; retirement of
  never-won / below-base-rate rules; no scope widening on merge; task-keyed retrieval;
  Anti-Pattern rules (`avoid.py`).
- Study with early gate (pilot removed): `experiment.py`, `cli.py`, `tools/run.ps1`
  (`study`, `status`, `plots`, `bakeoff`; flags `-GateAt 75 -GateMargin 0 -PastGate -RestartLibrary`).
  Restart keeps C/D games only if the C/D probe (`probe.json`) matches.
- Reports: `tools/mini_practice.py`, `tools/manual_check.py`; results so far in `results/`
  (`library-comparison.md`, `mini-macla-*`, `study-E-library-at-gate.txt`).
- Archived runs in WSL `/root/ll-runs/old-*`; current study folder `/root/ll-runs/study` (gate
  failed 20 vs 21 with the older library; restart with `-RestartLibrary`).

## Environment
- WSL Ubuntu-24.04 as root, venv `/root/venvs/living`; runs in `/root/ll-runs`; manifest
  `/root/ll-runs/manifest.json`. Tests: `wsl.exe -d Ubuntu-24.04 -u root -- bash -lc "cd
  '/mnt/c/Git Repos/living-library-experiment' && /root/venvs/living/bin/python -m unittest discover -s tests"`.
- Model: Qwen3.5-9B Q4_K_M, server `tools/serve-model.ps1` (port 8000, 24 slots, -ub 4096). Start it
  hidden: `Start-Process powershell -WindowStyle Hidden -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','"C:\Git Repos\living-library-experiment\tools\serve-model.ps1"'`.
  `run.ps1` and `when-idle-check.ps1` start/stop it themselves. Never close their windows.
- Rules: no `find`/recursive scans over drives; `lc` only for large jobs; never print the VM
  password; don't delete the Qwen3-8B model file; keep C at or below 80% success.

## Useful commands
- Print a library from checkpoints: the scratch script logic is: load the last
  `checkpoints/<stream>/NNNNN.json`, print `memory.rules` (id, type, task_type, alpha/beta, text) and
  count manual ops/errors over all records. Put such a script in `tools/show_library.py` if missing.
- `tools\run.ps1 status`; `nvidia-smi`; `Get-Content $env:TEMP\when-idle-check.log -Tail 5`.
