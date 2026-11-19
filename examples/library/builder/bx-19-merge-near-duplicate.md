# A new rule merged into an existing one

- Run `practice-d`, stream `practice-E-0`, practice game #45. Condition E.
- Goal: **find two laptop and put them in ottoman.**   Kind: two objects
- *What it shows:* The Builder writes a rule; code finds a near-duplicate (similarity >= 0.75) of the same type and kind and merges it into rule_6 ("merged a new rule into rule_6") instead of adding a second rule; its task is kept as extra evidence.

## 1. The practice game (first attempt)

Outcome: **LOST** in 30 steps (1 invalid).

Rules shown to the agent in this game (from the manual before the game):

- `rule_21` **Success Process** Beta(2,2): When an object must be placed on a surface: search all surfaces first, open the target if closed, go to the target location, take the object from its source, go to the target location, move the object to the target.
- `rule_22` **Corrected Error** Beta(7,8): When placing a hot object on a countertop, heat it with a microwave first, then move it to the countertop.

Actions (`!` marks an invalid command):

```
go to drawer 1 | open drawer 1 | go to drawer 2 | open drawer 2 | go to drawer 3 | go to drawer 4 | open drawer 4 | go to drawer 5 | open drawer 5 | go to drawer 6 | open drawer 6 | go to ottoman 1 | go to armchair 1 | go to coffeetable 1 | take laptop 1 from coffeetable 1 | !move laptop 1 to ottoman 1 | go to drawer 1 | go to drawer 2 | go to drawer 3 | go to drawer 4 | go to drawer 5 | go to drawer 6 | go to diningtable 1 | go to coffeetable 1 | go to drawer 1 | go to armchair 1 | go to garbagecan 1 | go to armchair 1 | examine armchair 1 | go to ottoman 1
```

## 2. Reflexion retries (ExpeL experience gathering)

A lost practice game is replayed from the start, up to 3 times, with the agent's own reflection on each failed attempt in its prompt; it stops at the first win. Retries change no memory.

**Attempt 1** (retry): lost in 30 steps.

Reflection on the previous failed attempt, given to the agent at the start of this attempt:

> "I failed because I only found one laptop on the coffeetable and tried to move it directly to the
> ottoman without checking if the ottoman could accept it or if I needed to find a second laptop
> first. I should have examined the ottoman 1 more carefully to see if it was empty and capable of
> holding items, and I need to search more thoroughly for the second laptop which might be in
> another location li"

```
go to drawer 1 | open drawer 1 | go to drawer 2 | open drawer 2 | go to coffeetable 1 | take laptop 1 from coffeetable 1 | go to ottoman 1 | move laptop 1 to ottoman 1 | go to drawer 3 | go to drawer 4 | open drawer 4 | go to drawer 5 | open drawer 5 | go to drawer 6 | open drawer 6 | go to armchair 1 | go to coffeetable 1 | go to drawer 1 | go to drawer 7 | open drawer 7 | go to diningtable 1 | go to drawer 1 | go to armchair 1 | go to coffeetable 1 | go to ottoman 1 | go to coffeetable 1 | go to drawer 1 | go to ottoman 1 | take laptop 1 from ottoman 1 | go to drawer 1
```

**Attempt 2** (retry): lost in 30 steps.

Reflection on the previous failed attempt, given to the agent at the start of this attempt (the list of reflections grows; the model often repeats itself):

> "I failed because I only found one laptop on the coffeetable and moved it to the ottoman without
> searching for the second laptop first. I should have continued searching all locations (drawers,
> tables, chairs) for the second laptop before attempting to move both to the ottoman. I need to
> systematically check every remaining location like drawer 3, drawer 4, drawer 5, drawer 6, drawer
> 7, armchair 1,"

```
go to coffeetable 1 | take laptop 1 from coffeetable 1 | go to ottoman 1 | move laptop 1 to ottoman 1 | go to drawer 1 | open drawer 1 | go to drawer 2 | open drawer 2 | go to drawer 3 | go to drawer 4 | open drawer 4 | go to drawer 5 | open drawer 5 | go to drawer 6 | open drawer 6 | go to drawer 7 | go to armchair 1 | go to drawer 1 | go to coffeetable 1 | go to diningtable 1 | go to garbagecan 1 | go to ottoman 1 | examine ottoman 1 | go to drawer 1 | go to drawer 2 | go to drawer 3 | go to drawer 4 | go to drawer 5 | go to drawer 6 | go to drawer 7
```

**Attempt 3** (retry): lost in 30 steps.

Reflection on the previous failed attempt, given to the agent at the start of this attempt (the list of reflections grows; the model often repeats itself):

> "I failed because I only found one laptop on the coffeetable and moved it to the ottoman without
> searching for the second laptop first. I should have systematically checked all remaining
> locations like drawer 3, drawer 4, drawer 5, drawer 6, drawer 7, and armchair 1 for the second
> laptop before attempting to move both to the ottoman. I need to continue searching all locations
> for the second laptop"

```
go to coffeetable 1 | take laptop 1 from coffeetable 1 | go to ottoman 1 | move laptop 1 to ottoman 1 | go to drawer 1 | open drawer 1 | go to drawer 2 | open drawer 2 | go to drawer 3 | go to drawer 4 | open drawer 4 | go to drawer 5 | open drawer 5 | go to drawer 6 | open drawer 6 | go to drawer 7 | open drawer 7 | close drawer 7 | go to armchair 1 | go to coffeetable 1 | go to diningtable 1 | go to coffeetable 1 | go to drawer 1 | go to garbagecan 1 | go to drawer 2 | go to drawer 3 | go to drawer 4 | go to drawer 5 | go to drawer 6 | go to drawer 7
```

Retry cost: 104 model calls, 275,163 tokens; retry won: **False**.

## 3. Builder report

Case: **failure**  (first attempt lost); diagnosis: imperfect rules

- `outcome` the game was LOST; Beta(alpha, beta) of the shown rules ['rule_21', 'rule_22'] updated (won: alpha+1, lost: beta+1); the won game's plan and steps are stored as evidence for the rules.
- `update_rule` rule_21  Validation note: _Agent failed to place peppershaker because it moved directly without going to target first; success required going to target before moving. | Agent failed to place laptop because it moved directly wit_
- `merge_rule` the new rule was merged into rule_6 (task `pick_two_obj_and_place` kept as extra evidence: "find two laptop and put them in ottoman.")
- `pool_game` this never-won game (4 attempts: the first and each failed retry) is pooled by kind of task (`pick_two_obj_and_place`) for Anti-Pattern mining.
- `refine` (MACLA contrastive refinement) rule_22 rewritten from its won and lost games (won/lost counts at refinement [3, 6]): "When placing two objects in a container: search drawers first, take both objects, move them to the container."

Log lines the Builder step produced (verbatim), with what they mean:

- `rule_21 keeps its text (a lost game may not rewrite a rule the agent sees)`
  - Guard: a lost game may not rewrite a rule the agent sees (only a validation note is added).
- `merged a new rule into rule_6`
  - Near-duplicate of an existing rule of the same type and kind: merged into it (counted as agreement, new task kept as evidence) instead of added.

## 4. What changed in the manual

- `rule_21` **beta**
  - before: [Success Process] Beta(2,2) visible=True: When an object must be placed on a surface: search all surfaces first, open the target if closed, go to the target location, take the object from its source, go to the target location, move the object to the target.
  - after:  [Success Process] Beta(2,3) visible=True: When an object must be placed on a surface: search all surfaces first, open the target if closed, go to the target location, take the object from its source, go to the target location, move the object to the target.
- `rule_22` **rule, beta**
  - before: [Corrected Error] Beta(7,8) visible=True: When placing a hot object on a countertop, heat it with a microwave first, then move it to the countertop.
  - after:  [Corrected Error] Beta(7,9) visible=True: When placing two objects in a container: search drawers first, take both objects, move them to the container.
