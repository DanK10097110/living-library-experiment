# Merge a near-duplicate and refine another rule in the same game

- Run `practice-b`, stream `practice-E-0`, practice game #24. Condition E.
- Goal: **put two keychain in drawer.**   Kind: two objects
- *What it shows:* Two-object task, retry 1 wins. The Builder writes a rule that is a near-duplicate of rule_5 and it is merged into it (counted as agreement). A new Success Process is written, and the contrastive refiner rewrites rule_10 from its won and lost games.

## 1. The practice game (first attempt)

Outcome: **LOST** in 30 steps (2 invalid).

Rules shown to the agent in this game (from the manual before the game):

- `rule_5` **Corrected Error** Beta(1,1): When objects must be retrieved and placed, search all possible locations systematically before attempting to complete the task.
- `rule_10` **Corrected Error** Beta(5,5): When the goal requires cooling an object, locate and take the object from a surface before attempting to open any cabinets.

Actions (`!` marks an invalid command):

```
go to drawer 1 | open drawer 1 | go to desk 1 | take keychain 3 from desk 1 | go to drawer 1 | go to desk 1 | examine desk 1 | go to drawer 2 | open drawer 2 | go to desk 1 | go to drawer 2 | open drawer 3 | !move keychain 3 to drawer 1 | go to desk 1 | go to drawer 1 | !examine desk 1 | go to bed 1 | go to desk 1 | examine desk 1 | go to drawer 1 | move keychain 3 to drawer 1 | examine drawer 1 | go to desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1
```

## 2. Reflexion retries (ExpeL experience gathering)

A lost practice game is replayed from the start, up to 3 times, with the agent's own reflection on each failed attempt in its prompt; it stops at the first win. Retries change no memory.

**Attempt 1** (retry): WON in 28 steps.

Reflection on the previous failed attempt, given to the agent at the start of this attempt:

> "I only found and moved one keychain (keychain 3) from desk 1 to drawer 1, but the goal requires
> two keychains. I should have examined the desk more thoroughly or checked other locations for a
> second keychain before giving up, as the desk initially showed multiple items that might have
> included another keychain or I missed it during my initial scan."

```
go to desk 1 | !go to desk 1 | take keychain 3 from desk 1 | examine desk 1 | go to drawer 1 | open drawer 1 | move keychain 3 to drawer 1 | go to drawer 2 | open drawer 2 | go to desk 1 | go to drawer 3 | go to desk 1 | examine desk 1 | examine desk 1 | go to drawer 3 | open drawer 3 | go to sidetable 1 | take keychain 1 from sidetable 1 | !move keychain 1 to drawer 1 | !go to sidetable 1 | !go to sidetable 1 | go to desk 1 | go to sidetable 1 | !take keychain 2 from sidetable 1 | !move keychain 2 to drawer 1 | go to drawer 1 | examine drawer 1 | move keychain 1 to drawer 1
```

Retry cost: 33 model calls, 81,904 tokens; retry won: **True**.

## 3. Builder report

Case: **corrected failure**  (first attempt lost, retry won); diagnosis: imperfect rules

- `outcome` the game was LOST; Beta(alpha, beta) of the shown rules ['rule_5', 'rule_10'] updated (won: alpha+1, lost: beta+1); the won game's plan and steps are stored as evidence for the rules.
- `merge_rule` the new rule was merged into rule_5 (task `pick_two_obj_and_place` kept as extra evidence: "put two keychain in drawer.")
- `write_rule` **Success Process** (kind `pick_two_obj_and_place`, verified=True): "When two keychains must be placed in a drawer: search desk and sidetable first, take keychains from surfaces, open the target drawer if closed, move each keychain to the drawer."  Example: _Search desk 1 and sidetable 1, take keychains, open drawer 1, move keychains to drawer 1._
- `pool_won` this won attempt is stored in the hidden failure pool of its kind of task (used to check Anti-Pattern candidates against wins).
- `refine` (MACLA contrastive refinement) rule_10 rewritten from its won and lost games (won/lost counts at refinement [4, 5]): "When an object must be placed in a container and multiple objects are needed, search the room for all objects first before opening the container."

Log lines the Builder step produced (verbatim), with what they mean:

- `merged a new rule into rule_5`
  - Near-duplicate of an existing rule of the same type and kind: merged into it (counted as agreement, new task kept as evidence) instead of added.

## 4. What changed in the manual

- `rule_5` **beta**
  - before: [Corrected Error] Beta(1,1) visible=True: When objects must be retrieved and placed, search all possible locations systematically before attempting to complete the task.
  - after:  [Corrected Error] Beta(1,2) visible=True: When objects must be retrieved and placed, search all possible locations systematically before attempting to complete the task.
- `rule_10` **rule, beta**
  - before: [Corrected Error] Beta(5,5) visible=True: When the goal requires cooling an object, locate and take the object from a surface before attempting to open any cabinets.
  - after:  [Corrected Error] Beta(5,6) visible=True: When an object must be placed in a container and multiple objects are needed, search the room for all objects first before opening the container.
- `rule_17` **NEW**
  - after:  [Success Process] Beta(1,1) visible=True: When two keychains must be placed in a drawer: search desk and sidetable first, take keychains from surfaces, open the target drawer if closed, move each keychain to the drawer.
