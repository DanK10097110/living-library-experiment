# Living Skill Library for Hierarchical Embodied Planning

A lean proof-of-concept testing whether a small open-source LLM agent that stores verified skills as code becomes more reliable and cheaper over a stream of tasks.

## Project Structure

```
living-library-experiment/
├── configs/
│   └── pilot.yaml              # Frozen experimental config (after week 2)
├── src/
│   └── living_skills/
│       ├── environment.py      # ALFWorld environment wrapper
│       ├── planner.py          # L1 high-level planner (heuristic + LLM)
│       ├── skill_writer.py     # L2 skill generator (heuristic + LLM)
│       ├── executor.py         # Safe skill execution + episode runner
│       ├── skill_library.py    # Append-only skill library (E-)
│       ├── predicates.py       # Simulator-grounded predicate checking
│       └── metrics.py          # Episode logging + pilot metrics
├── scripts/
│   ├── smoke_test.py           # Basic ALFWorld connectivity test
│   ├── integration_test.py     # Full M1-M5 pipeline test
│   └── run_pilot.py            # M7: 300-episode pilot runner (C vs E-)
├── tests/
├── results/
├── requirements.txt
└── README.md
```

## Setup

1. **Prerequisites**: Python 3.10+, ALFWorld installed with data in `~/.cache/alfworld/json_2.1.1/`

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Verify ALFWorld integration**:
   ```bash
   python scripts/smoke_test.py
   ```

4. **Run integration test**:
   ```bash
   python scripts/integration_test.py
   ```

5. **Run pilot experiments**:
   ```bash
   # Quick dry-run (5 episodes for C and E-)
   python scripts/run_pilot.py --condition both --dry-run

   # Run full 300 practice episodes for System E-
   python scripts/run_pilot.py --condition E- --episodes 300

   # Run 140 evaluation episodes on valid_seen for System C
   python scripts/run_pilot.py --condition C --split valid_seen --episodes 140
   ```

## Phase 1 — Pilot (Weeks 1–2)

The pilot builds a hierarchical agent with an append-only skill library (E⁻) and runs 300 practice episodes on ALFWorld to determine if the benchmark is suitable for the full study.

### Systems under test

| ID | Condition | Memory |
|----|-----------|--------|
| C  | Hierarchy, no memory | None |
| E⁻ | Hierarchy + append-only skill library | Skills saved but never updated |

### Pilot decision rules

| Check | Threshold | Action |
|-------|-----------|--------|
| Task success (C or E⁻) | >85% | Switch to ScienceWorld |
| Skills reused ≥5 times | <10 | Switch to ScienceWorld |
| False-success rate | >10% | Tighten verification |
| L2 crash/reject rate | >40% | Improve skill generation |

## Architecture

Two-level LLM hierarchy with three checks and one update gate:

- **L1 (Planner)**: Breaks tasks into ordered subgoals. Sees only skill names and signatures.
- **L2 (Skill Writer)**: Generates executable Python skills for individual subgoals. Sees full code and failure notes.
- **Executor**: Runs skills in a sandbox, checks pre/postconditions against simulator state.
- **Skill Library**: Stores verified skills with typed contracts, outcome counts, and regression tests.
