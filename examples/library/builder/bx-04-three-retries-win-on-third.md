# Three retries, win on the third: the reflection repeats itself

- Run `practice-b`, stream `practice-E-0`, practice game #20. Condition E.
- Goal: **put a hot potato in diningtable.**   Kind: heat then place
- *What it shows:* A hot-potato task fails the first attempt and retries 1 and 2, then wins on retry 3 (13 steps). The reflections for attempts 2 and 3 are nearly identical. The winning attempt finally uses `heat potato 1 with microwave 1`. The Builder writes a Corrected Error and a Success Process.

## 1. The practice game (first attempt)

Outcome: **LOST** in 30 steps (6 invalid).

Rules shown to the agent in this game (from the manual before the game):

- `rule_7` **Corrected Error** Beta(1,1): When a stoveburner already has a kettle on it, never place a mug on the stoveburner to heat it; use the microwave instead.
- `rule_10` **Corrected Error** Beta(2,4): When the goal requires cooling an object, locate and take the object from a surface before attempting to open any cabinets.

Actions (`!` marks an invalid command):

```
go to fridge 1 | open fridge 1 | go to countertop 1 | go to diningtable 1 | take potato 1 from diningtable 1 | go to stoveburner 1 | !put potato 1 on stoveburner 1 | examine stoveburner 1 | go to microwave 1 | open microwave 1 | move potato 1 to microwave 1 | close microwave 1 | open microwave 1 | close microwave 1 | open microwave 1 | take potato 1 from microwave 1 | !move potato 1 to diningtable 1 | move potato 1 to microwave 1 | close microwave 1 | go to stoveburner 1 | !move potato 1 to stoveburner 1 | !move potato 1 to diningtable 1 | !move potato 1 to diningtable 1 | go to microwave 1 | !move potato 1 to diningtable 1 | go to sinkbasin 1 | go to diningtable 1 | take potato 2 from diningtable 1 | go to microwave 1 | open microwave 1
```

## 2. Reflexion retries (ExpeL experience gathering)

A lost practice game is replayed from the start, up to 3 times, with the agent's own reflection on each failed attempt in its prompt; it stops at the first win. Retries change no memory.

**Attempt 1** (retry): lost in 30 steps.

Reflection on the previous failed attempt, given to the agent at the start of this attempt:

> "I failed because I repeatedly moved the potato to the stoveburner and microwave instead of
> directly placing it on the diningtable, and I got stuck at the stoveburner trying to move the
> potato there when it was already in my inventory. I should have immediately moved the potato 1 to
> diningtable 1 after picking it up from the microwave, or taken potato 2 directly from the
> diningtable and placed it b"

```
go to fridge 1 | go to countertop 1 | go to fridge 1 | go to countertop 1 | go to diningtable 1 | take potato 1 from diningtable 1 | go to microwave 1 | open microwave 1 | move potato 1 to microwave 1 | close microwave 1 | open microwave 1 | take potato 1 from microwave 1 | move potato 1 to microwave 1 | close microwave 1 | open microwave 1 | !move potato 1 to microwave 1 | !move potato 1 to diningtable 1 | !move potato 1 to diningtable 1 | !The agent is stuck in a loop of moving the potato to the microwave and diningtable without successfully heating it. The potato is currently in the inventory (picked up in step 12), and the agent needs to place it inside the microwave to heat it. Since the last action 'move potato 1 to | !move potato 1 to microwave 1 | !go to microwave 1 | go to diningtable 1 | go to microwave 1 | take potato 1 from microwave 1 | move potato 1 to microwave 1 | close microwave 1 | !move potato 1 to microwave 1 | !close microwave 1 | open microwave 1 | !move potato 1 to diningtable 1
```

**Attempt 2** (retry): lost in 30 steps.

Reflection on the previous failed attempt, given to the agent at the start of this attempt (the list of reflections grows; the model often repeats itself):

> "I failed because I repeatedly moved the potato between the microwave and diningtable without
> successfully heating it, and I got stuck in a loop of invalid move attempts. I should have closed
> the microwave after placing the potato inside, waited for it to heat, then moved the potato
> directly to diningtable 1 without reopening the microwave unnecessarily. I need to ensure the
> potato is heated before"

```
go to fridge 1 | go to countertop 1 | go to fridge 1 | go to diningtable 1 | take potato 1 from diningtable 1 | go to microwave 1 | open microwave 1 | move potato 1 to microwave 1 | close microwave 1 | !wait | open microwave 1 | take potato 1 from microwave 1 | go to diningtable 1 | move potato 1 to diningtable 1 | !done | examine diningtable 1 | !The potato is already on the diningtable and was just heated in the microwave, so the task of putting a hot potato on the diningtable should be complete. Since the previous attempts failed due to loops or incorrect placement, and the current state shows the potato is on the table, I should verify the task is | examine diningtable 1 | !done | !done | examine diningtable 1 | !done | examine diningtable 1 | go to microwave 1 | go to diningtable 1 | take potato 1 from diningtable 1 | move potato 1 to diningtable 1 | go to microwave 1 | close microwave 1 | open microwave 1
```

**Attempt 3** (retry): WON in 13 steps.

Reflection on the previous failed attempt, given to the agent at the start of this attempt (the list of reflections grows; the model often repeats itself):

> "I failed because I repeatedly moved the potato between the microwave and diningtable without
> successfully heating it, and I got stuck in a loop of invalid move attempts. I should have closed
> the microwave after placing the potato inside, waited for it to heat, then moved the potato
> directly to diningtable 1 without reopening the microwave unnecessarily. I need to ensure the
> potato is heated before"

```
go to fridge 1 | go to countertop 1 | go to fridge 1 | go to countertop 1 | go to fridge 1 | go to diningtable 1 | take potato 1 from diningtable 1 | go to microwave 1 | open microwave 1 | heat potato 1 with microwave 1 | close microwave 1 | go to diningtable 1 | move potato 1 to diningtable 1
```

Retry cost: 89 model calls, 271,562 tokens; retry won: **True**.

## 3. Builder report

Case: **corrected failure**  (first attempt lost, retry won); diagnosis: imperfect agent

- `outcome` the game was LOST; Beta(alpha, beta) of the shown rules ['rule_7', 'rule_10'] updated (won: alpha+1, lost: beta+1); the won game's plan and steps are stored as evidence for the rules.
- `write_rule` **Corrected Error** (kind `pick_heat_then_place_in_recep`, verified=True): "When heating an object in a microwave, use the heat command instead of move to place it inside."  Example: _The agent failed by moving the potato to the microwave; it should have used heat potato 1 with microwave 1._
- `write_rule` **Success Process** (kind `pick_heat_then_place_in_recep`, verified=True): "When a hot potato must be placed in a diningtable: search diningtable first, take the potato, go to microwave, heat potato with microwave, close microwave, go to diningtable, move potato to diningtable."  Example: _The agent took potato 1 from diningtable 1, heated it with microwave 1, then moved it to diningtable 1._
- `pool_won` this won attempt is stored in the hidden failure pool of its kind of task (used to check Anti-Pattern candidates against wins).

## 4. What changed in the manual

- `rule_7` **beta**
  - before: [Corrected Error] Beta(1,1) visible=True: When a stoveburner already has a kettle on it, never place a mug on the stoveburner to heat it; use the microwave instead.
  - after:  [Corrected Error] Beta(1,2) visible=True: When a stoveburner already has a kettle on it, never place a mug on the stoveburner to heat it; use the microwave instead.
- `rule_10` **beta**
  - before: [Corrected Error] Beta(2,4) visible=True: When the goal requires cooling an object, locate and take the object from a surface before attempting to open any cabinets.
  - after:  [Corrected Error] Beta(2,5) visible=True: When the goal requires cooling an object, locate and take the object from a surface before attempting to open any cabinets.
- `rule_15` **NEW**
  - after:  [Corrected Error] Beta(1,1) visible=True: When heating an object in a microwave, use the heat command instead of move to place it inside.
- `rule_16` **NEW**
  - after:  [Success Process] Beta(1,1) visible=True: When a hot potato must be placed in a diningtable: search diningtable first, take the potato, go to microwave, heat potato with microwave, close microwave, go to diningtable, move potato to diningtable.
