MATCHED ALFWORLD TASK COMPARISONS
================================

Open alfworld-episodes.html in a browser. It is self-contained and works offline.

Three tabs, each the same game played without the library (C) and with it (E).
C and E use the same model, planner, actor and 30-action budget; E additionally
gets a few rules retrieved from its learned library. Every tab lists all rules
E received, verbatim. Caveat: the C replays come from an earlier evaluation run
(old-pilot-9b-v1) than the E replays (check-d / check-e libraries).

1. Place a watch. C: not met in 30 actions (opens drawers, never checks the
   coffee table). E: met in 8. Rule: "search surfaces first, then containers".

2. Two objects (tissue boxes on the toilet). C: one box placed, not met in 30
   (searches drawers first; tries a placement without walking to the toilet,
   refused). E: both placed in 8. Rules: "search surfaces before drawers",
   "navigate to the target before each move command".

3. Bowl & lamp. Both succeed: C in 14 actions (puts the bowl down, loops on
   examine), E in 3. Rule: take the object, use the light source at its location.

How to present
--------------
Defaults: side by side, every action, 2x speed. Guided checkpoints jumps between
the key decisions.

Every action shows the complete replays at a shared action index. A replay
that has finished keeps its final frame visible while the other continues.

Choose One after another to play every action of the first recording, reset the
scene, then play the second recording. Chapter buttons jump between recordings.

Space: play or pause. Left / Right: step through checkpoints or actions.
The timeline jumps directly to a position. F: full screen. Speed changes pacing.
Inspect rules & source records shows the actual rules, reflection, subsequent
rule update, and exact source paths. How to read this explains the comparisons.

Recording and validation
------------------------
Every TextWorld action-validity flag
and all final outcomes match the saved source records. The final 3D
outcomes also match. Each pair shares the same game ID and game-file SHA-256.
The C and E replays are separate evaluation runs.

RGB images are real renders from ALFWorld 0.4.2 / AI2-THOR 2.1.0. Official ALFRED
object placements are restored for each replay. The oracle grounds abstract
commands using physical entity IDs, teleport viewpoints, and the official
forceAction API, including occluded objects. This visualizes recorded abstract
policies; it does not evaluate a new perception or navigation policy.

Commands rejected by TextWorld remain visible in the replay but are not sent
to the physical controller. This prevents forceAction from accepting a remote
placement that the source environment rejected. The per-step
thor_command_dispatched field records this choice in new captures. If a saved
oracle viewpoint is blocked by a restored object, navigation tries nearby
official viewpoints with normal collision checks. No object placement or goal
flag is changed to manufacture a success. If opening a drawer lets an item
slip out, the oracle can use that item's original restored parent relation to
ground a source-valid pickup. The pickup itself still uses the physical API.

TextWorld names are mapped to physical IDs; its move ... to command is expressed
as the THOR controller's equivalent put ... in command. Both strings are kept.
Simulator task checks determine the physical goal result. No new model
inference, weight training, or video recording is performed.

These selected cases illustrate behavior rather than establish an overall
benchmark result or a causal effect of an individual rule.

Files
-----
alfworld-episodes.html: complete interactive demo with embedded images.
alfworld-replay.json: matched cases, source hashes, action records, and outcomes.
alfworld-tools/alfworld-comparisons.json: source selection and guided checkpoints.
alfworld-tools/replay_cases.py: adapters for episode and practice/retry records.
alfworld-tools/render_alfworld_episodes.py: engine replay and capture.
alfworld-tools/build_alfworld_demo.py: self-contained demo packaging.
alfworld-tools/alfworld-demo.template.html: comparison interface.
alfworld-tools/requirements.txt: simulator dependencies.

Reproduce from the repository root
----------------------------------
python3 -m venv .venv-alfworld
.venv-alfworld/bin/python -m pip install -r visualization/alfworld-tools/requirements.txt
.venv-alfworld/bin/alfworld-download --data-dir work/alfworld-data
.venv-alfworld/bin/python visualization/alfworld-tools/render_alfworld_episodes.py --repo . --data-root work/alfworld-data/json_2.1.1 --cache-root work/ai2thor-cache --output work/alfworld-captures
.venv-alfworld/bin/python visualization/alfworld-tools/build_alfworld_demo.py --captures work/alfworld-captures --output visualization

Add --reuse to the renderer to reuse captures with unchanged source hashes.
Use --only EPISODE_ID (or comma-separated IDs) to regenerate selected replays. --selection
accepts another compatible comparison manifest.

The first render downloads the official AI2-THOR build into --cache-root and
checks its upstream SHA-256. The legacy macOS build runs through Rosetta on
Apple Silicon. Viewing the finished demo does not need the simulator installed.

Engine and data: https://github.com/alfworld/alfworld
