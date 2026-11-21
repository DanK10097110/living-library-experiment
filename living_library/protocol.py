"""Pre-registration of the current design (redesign 2026-11-20), with a short amendment history.
Expectations come from the proposal; they are not empirical claims about this run."""

PREREGISTRATION = {
    "conditions": {
        "C": "planner + published ALFWorld ReAct actor, no memory",
        "D": "C + successful first-attempt practice trajectories; the top 3 by goal similarity shown as examples",
        "E": "C + rule manual built in practice with evidence-based management (LIBRARY-SPEC.md)",
        "E-minus": "E with the same writing, judging and ranking, but append-only (never changes or removes a rule)",
        "A": "flat ReAct without planner or memory; kept in the code, not part of the study",
    },
    "data": "Practice: 300 games per memory condition and replicate from the ALFWorld train split. Out-of-distribution "
            "test (primary): the 134 unseen-room games. In-distribution test (secondary, same analysis): the 70 "
            "seen-room games outside the development set. Development set: the other 70 seen-room games, used "
            "only for the early gate and offline library checks. One evaluation seed (11).",
    "replicates": "Practice seeds [0, 1]: every memory condition practises once per seed, each seed with its own game "
                  "order (shared by D, E and E-minus, so practice games are paired within a replicate). Each "
                  "replicate's memory is evaluated on the same test games.",
    "frozen_evaluation": "Every test (evaluation, gate, snapshots) reads the practice memory frozen: nothing is "
                         "learned at test time, so test episodes are independent.",
    "practice": "Batches of 8 games run on the memory as it was at the start of the batch and are merged in fixed "
                "position order (batching.py); each game is its own episode.",
    "retries": "Part of the library method for E and E-minus only (ExpeL experience gathering with Reflexion): a lost "
               "practice game is replayed with a short reflection on each failed attempt, up to 3 retries, stopping "
               "at the first win; retries read the memory and change nothing, and their calls and tokens are charged "
               "to the game. Asymmetry, stated: D stores first-attempt wins only, so H1 compares 'rules + retries' "
               "with 'trajectories without retries'. Practice success uses the first attempt only. Never in tests.",
    "hypotheses": {
        "H1": {"comparison": "E - D", "metric": "task_success", "expectation": "no confident prediction"},
        "H2": {"comparison": "E - D", "metric": "amortized_weighted_tokens_per_task",
               "expectation": "E costs less including practice"},
        "H3": {"comparison": "E - E-minus", "metric": "task_success",
               "expectation": "rule management helps; a smaller gain than adding memory"},
    },
    "secondary": "E - C task success (memory helps); the same analysis on the in-distribution test.",
    "success_criterion": "(E - D task success >= 10 percentage points, OR zero inside its 95% CI with >= 30% lower "
                         "amortized cost) AND H3 > 0 with Holm-adjusted p <= .05.",
    "statistics": "Hierarchical paired percentile bootstrap: each sample resamples the evaluation tasks and, within "
                  "each condition, its practice replicates with replacement; a task's value is the mean over the "
                  "chosen replicates and the evaluation seeds. Cost = weighted tokens (input + 4 x output) per task; "
                  "each replicate's practice cost (retries included) is amortized over its evaluation tasks. Centered "
                  "two-sided bootstrap p values; Holm correction over H1-H3.",
    "early_gate": "A bug detector, not evidence: library practice stops at 75 games, then E (replicate 0, frozen) "
                  "plays 30 development games against C; the study stops if E wins - C wins < -3. Gate games are "
                  "never part of H1-H3.",
    "sanity_rule": "If E - C is near zero, inspect retrieval, rule citations and Builder logs before interpreting a null result.",
    "amendments": {
        "2026_11_14_lean_design": "For local compute: condition B dropped, 300 practice games per memory condition "
                                  "(proposal: 500); H2 cost is weighted tokens instead of GPU-seconds (per-request GPU "
                                  "time is not observable on a batching server; cached replays must cost the same).",
        "2026_11_15_rule_manual": "Code skills failed with the 9B model (81% of candidates unverifiable); the E library "
                                  "became an AutoManual-style rule manual; one evaluation seed; frozen evaluation; "
                                  "OOD (primary) and ID (secondary) tests; condition A dropped from the study.",
        "2026_11_17_early_gate_and_retries": "The separate pilot was replaced by the early gate inside the study; "
                                             "Reflexion retries for E and E-minus practice; a library restart may keep "
                                             "C's and D's games when only library code changed or a fixture probe "
                                             "shows C and D unchanged.",
        "redesign_2026_11_20": "Code skills removed everywhere (interpreter, skill actions, E-plus, condition B and "
                               "E-text, invocation metrics); H3 is scored on task success (it was skill-invocation "
                               "success); H4 (E vs E-text) dropped; two practice replicates with a hierarchical "
                               "bootstrap; evidence-based rule management per LIBRARY-SPEC.md (outcome-blind "
                               "per-rule judge, evidence-triggered refinement capped at 2 revisions, retirement of "
                               "unfollowed or persistently harmful rules); the early gate became a bug detector "
                               "(margin -3); fresh output directory, C and D re-run because their prompts changed.",
        "evidence_2026_11_20": "The per-rule LLM judge was measured on gold-labelled archived games and removed "
                               "(it missed harmful rules and leaked the outcome). A rule's evidence: a short call "
                               "cites the rules each plan follows; harm is read from the trace (rejected prescribed commands, "
                               "loops, empty search places); a refinement must pass up to 3 frozen trial replays "
                               "before it replaces a text. Thresholds re-checked in the simulator (BAD_MEAN -0.4, "
                               "USELESS_MIN 16).",
        "d_one_replicate_2026_11_21": "Owner: use less compute. D (memory baseline) runs practice replicate 0 only; "
                                      "E and E-minus keep two. D's replicate-1 streams (practice 18 games, no "
                                      "evaluations yet) were dropped from study2 (tools/drop_streams.py); C's "
                                      "remaining evaluation games replay the earlier run's cached responses "
                                      "(memoryless, identical requests).",
        "builder_2026_11_21": "Builder input gains computed game facts, numbered steps and latest notes only; "
                              "refused rule operations go back once with the reasons; a lost game with a won "
                              "attempt of its kind may write one Corrected Error, kept only if one frozen trial "
                              "replay of the task uses it without harm; a loose grounding check. Measured with "
                              "Claude-graded A/B checks (results/builder-check). E and E-minus practice restarted.",
    },
}
