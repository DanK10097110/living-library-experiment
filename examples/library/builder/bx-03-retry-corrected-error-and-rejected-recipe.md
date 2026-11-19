# Retry win writes a Corrected Error; a recipe naming a numbered object is rejected

- Run `practice-b`, stream `practice-E-0`, practice game #4. Condition E.
- Goal: **put a hot mug in coffeemachine.**   Kind: heat then place
- *What it shows:* Heat task lost then won on retry 1. The Builder writes a Corrected Error ("never place a mug on the stoveburner to heat it; use the microwave instead") and its Success Process attempt is rejected by the code check because the text names "microwave 1".

## 1. The practice game (first attempt)

Outcome: **LOST** in 30 steps (6 invalid).

Rules shown to the agent in this game (from the manual before the game):

- none (no rule of this kind existed yet)

Actions (`!` marks an invalid command):

```
go to drawer 1 | go to drawer 2 | go to countertop 1 | go to stoveburner 1 | go to countertop 1 | take mug 1 from countertop 1 | go to stoveburner 1 | examine stoveburner 1 | !place mug 1 on stoveburner 1 | examine stoveburner 1 | examine stoveburner 1 | examine stoveburner 1 | examine stoveburner 1 | go to stoveburner 2 | go to stoveburner 1 | examine stoveburner 1 | examine mug 1 | examine stoveburner 1 | examine stoveburner 1 | examine stoveburner 1 | examine stoveburner 1 | examine stoveburner 1 | examine stoveburner 1 | !examine kettle 1 | examine stoveburner 1 | !examine kettle 1 | !examine kettle 1 | examine stoveburner 1 | !examine kettle 1 | !examine kettle 1
```

## 2. Reflexion retries (ExpeL experience gathering)

A lost practice game is replayed from the start, up to 3 times, with the agent's own reflection on each failed attempt in its prompt; it stops at the first win. Retries change no memory.

**Attempt 1** (retry): WON in 7 steps.

Reflection on the previous failed attempt, given to the agent at the start of this attempt:

> "I attempted to place the mug on the stoveburner to heat it, but the action was invalid because
> the stoveburner already had a kettle on it. Instead, I should have examined the stoveburner more
> carefully to understand why the mug couldn't be placed, or looked for an alternative way to heat
> the mug such as using the kettle to boil water for it. I also wasted many steps repeatedly
> examining the stoveb"

```
go to fridge 1 | open fridge 1 | go to countertop 1 | take mug 1 from countertop 1 | go to microwave 1 | open microwave 1 | heat mug 1 with microwave 1
```

Retry cost: 9 model calls, 21,558 tokens; retry won: **True**.

## 3. Builder report

Case: **corrected failure**  (first attempt lost, retry won); diagnosis: imperfect rules

- `outcome` the game was LOST; Beta(alpha, beta) of the shown rules [] updated (won: alpha+1, lost: beta+1); the won game's plan and steps are stored as evidence for the rules.
- `write_rule` **Corrected Error** (kind `pick_heat_then_place_in_recep`, verified=True): "When a stoveburner already has a kettle on it, never place a mug on the stoveburner to heat it; use the microwave instead."  Example: _The agent tried to place the mug on stoveburner 1 but failed because a kettle was already there. The agent then used the microwave to heat the mug successfully._
- `pool_won` this won attempt is stored in the hidden failure pool of its kind of task (used to check Anti-Pattern candidates against wins).

Log lines the Builder step produced (verbatim), with what they mean:

- `rejected Success Process text, names a numbered object ('microwave 1'): When a mug must be heated and placed in a coffeemachine: search countertop and f`
  - Code check: a rule must not name a numbered object ("microwave 1"); one rewrite is not attempted for this, text is rejected.

## 4. What changed in the manual

- `rule_7` **NEW**
  - after:  [Corrected Error] Beta(1,1) visible=True: When a stoveburner already has a kettle on it, never place a mug on the stoveburner to heat it; use the microwave instead.

- This run (practice-b) predates the specificity check, so the Corrected Error still names a kettle and a mug; later runs would rewrite or reject it (see bx-10).