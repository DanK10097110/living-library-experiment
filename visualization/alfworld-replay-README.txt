ALFWORLD 3D EPISODE REPLAYS
==========================

Open alfworld-episodes.html in a browser. It is self-contained and works offline.
Use Full screen when presenting the interactive demo.
The demo, controls, and captions are all in English.

Four recorded episodes are replayed:
  C / heating a mug: 30 actions, goal not met.
  E / heating a mug: 8 actions, goal met.
  E / cleaning a butter knife: 6 actions, goal met.
  E / holding a bowl with a desk lamp on: 3 actions, goal met.

Controls
--------
Play / Pause or Space: automatic playback.
Left / Right: previous or next high-level action.
Timeline: jump directly to an action.
Compare C / E or C: view the heating policies side by side.
Action detail: inspect the physical subactions inside commands such as heat.
Full screen or F: presentation mode.
Replay notes: source, engine, and interpretation details.

What is recorded and what is regenerated
---------------------------------------
The policy actions, original outcomes, and available rules come from examples/.
These were separate saved experiment runs; this is not the practice-g report.
RGB images were newly rendered with ALFWorld 0.4.2 / AI2-THOR 2.1.0.
The official ALFRED scenes and object placements are restored for each replay.
The same commands are replayed separately in TextWorld. All 47 recorded action
validity flags and all four final outcomes match that replay. All four final
3D task outcomes also agree with the saved recordings.

This is an oracle visualization of abstract policy actions. Navigation grounds
commands using ALFRED teleport viewpoints, including object-focused viewpoints
for a following pickup. The oracle uses ground-truth entity IDs and the official
forceAction interaction API; the occluded bowl is grounded this way. This does
not measure the performance of a new visual perception or navigation policy.
No new Qwen inference is performed, and no model weights are trained.

TextWorld and THOR number objects differently. The replay maps canonical
TextWorld names to physical IDs. TextWorld's "move ... to" is translated to
the official THOR oracle's equivalent "put ... in". Source command strings
and translated strings are both preserved. The simulator computes the physical
goal result. No success flag or physical scene state is fabricated.

Heating expands into several simulator subactions. In this recorded trace the
microwave is already open, so the oracle's redundant OpenObject subaction can
fail while subsequent heating and placement still satisfy the physical goal.

alfworld-replay.json records source file hashes, source run IDs, per-action
observations, validity, engine subactions, physical state summaries, and both
engines' final goal results. Its frame IDs address images embedded in the HTML.

Reproduce from the repository root
----------------------------------
1. Create a Python 3.11 environment and install:
   python3 -m venv .venv-alfworld
   .venv-alfworld/bin/python -m pip install -r visualization/alfworld-tools/requirements.txt

2. Obtain the official ALFWorld data:
   .venv-alfworld/bin/alfworld-download --data-dir work/alfworld-data
   The standard downloader also downloads detector weights. This oracle replay
   does not use those weights. Only the three scenes referenced by the selected
   examples are needed by the renderer.

3. Capture the episodes:
   .venv-alfworld/bin/python visualization/alfworld-tools/render_alfworld_episodes.py --repo . --data-root work/alfworld-data/json_2.1.1 --cache-root work/ai2thor-cache --output work/alfworld-captures

4. Build the interactive demo:
   .venv-alfworld/bin/python visualization/alfworld-tools/build_alfworld_demo.py --captures work/alfworld-captures --output visualization

The first render downloads the official AI2-THOR build into --cache-root and
checks its upstream SHA-256. On Apple Silicon, the legacy macOS Unity build
runs through Rosetta. Rendering needs a compatible graphics session; viewing
the finished HTML demo does not need ALFWorld installed.

Upstream engine and data:
https://github.com/alfworld/alfworld

Recorded examples:
examples/episodes/paired/pair-heat-mug-cabinet.json
examples/episodes/e/e-win-clean-fast.json
examples/episodes/e/e-win-look-3-steps.json
