MATCHED ALFWORLD TASK COMPARISONS
================================

Open alfworld-episodes.html in a browser. It is self-contained and works offline.
The demo and every control, caption, and explanation are in English.

The six tabs each compare two recordings of the exact same task instance:

1. Heat a mug: C (no memory) versus E (rule library).
   C: goal not met in 30 actions. E: goal met in 8 actions.
   The guided checkpoints show pickup, the stove/microwave decision, heating,
   and the two final outcomes. The one rule shown to E concerns navigation;
   the microwave route appears in the planner's output.

2. Bowl and lamp: C versus E.
   Both succeed: C takes 14 actions, E takes 3.
   The comparison shows C putting the bowl down and repeatedly examining the
   desk, while E keeps holding the bowl and turns the lamp on directly.

3. Reflect and retry: a chronological first attempt and retry of one practice game.
   Initial attempt: goal not met in 30 actions. Retry: goal met in 10 actions.
   The reflection is supplied before the retry. The rule manual is fixed during
   retries. A new Success Process is written after the retry succeeds, so the
   new rule is not presented as the cause of that retry's success.

4. Two objects: C versus successful E (check-e).
   C: goal not met in 30 actions. E: goal met in 8 actions.
   The task requires two tissue boxes on the toilet. C completes one valid
   delivery; E completes both. The Placed counter reflects physical object
   locations in the simulator, not the number of attempted placement commands.

5. Place a watch: C versus successful E (check-d).
   C: goal not met in 30 actions. E: goal met in 8 actions.
   E searches furniture surfaces, finds the watch on the coffee table, and
   delivers it to the side table. This E run uses the check-d library; it is
   not a condition D run.

6. Heat tomato: C versus successful E (check-avoid70).
   C: goal not met in 30 actions. E: goal met in 23 actions.
   E eventually heats and delivers the tomato, but repeatedly opens and closes
   the microwave first. This is a verified success, not an optimal solution.

The three added cases were selected for successful E outcomes. Their matching
C baselines may fail. Each added E win was also reproduced in the 3D engine.
The demo opens on the new Two objects comparison; the original tabs remain.

How to present
--------------
Side by side is the default. Press Play guided tour to move through meaningful
decision checkpoints. Checkpoints can align different action numbers, which
remain visible on each side. The What changed cards identify the input context,
observed strategy, and recorded result.

Choose Every action for the complete replays at a shared action index. A replay
that has finished keeps its final frame visible while the other continues.

Choose One after another to play every action of the first recording, reset the
scene, then play the second recording. Chapter buttons jump between recordings.

Space: play or pause. Left / Right: step through checkpoints or actions.
The timeline jumps directly to a position. F: full screen. Speed changes pacing.
Inspect rules & source records shows the actual rules, reflection, subsequent
rule update, and exact source paths. How to read this explains the comparisons.

Recording and validation
------------------------
Twelve replays contain 224 recorded actions. Every TextWorld action-validity flag
and all twelve final outcomes match the saved source records. The twelve final 3D
outcomes also match. Each pair shares the same game ID and game-file SHA-256.
The five C/E cases are separate evaluation runs, not successive training stages.
The practice case is a genuine initial-attempt/retry progression.

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
