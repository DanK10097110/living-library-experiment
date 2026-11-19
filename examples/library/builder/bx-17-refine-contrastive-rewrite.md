# MACLA contrastive refinement of a rule

- Run `study`, stream `practice-E-0`, practice game #27. Condition E.
- Goal: **put some pen on drawer.**   Kind: pick and place
- *What it shows:* rule_7 has now been shown in enough won and lost games since its last refinement. The model compares them and rewrites the rule as one tighter rule (an exclusion goes into the condition); the log records `refine`.

## 1. The practice game (first attempt)

Outcome: **LOST** in 22 steps (0 invalid).

Rules shown to the agent in this game (from the manual before the game):

- `rule_7` **Success Process** Beta(6,3): When an object must be picked up and placed: search cabinets first, take the object, go to the target, open the target if closed, move the object there.
- `rule_3` **Special Phenomenon** Beta(3,2): When placing an object on a surface, ensure the surface is open before attempting to place.

Actions (`!` marks an invalid command):

```
go to desk 1 | go to drawer 1 | go to desk 1 | go to drawer 1 | go to desk 1 | go to drawer 1 | open drawer 1 | go to desk 1 | go to drawer 1 | go to drawer 2 | go to desk 1 | go to drawer 1 | go to desk 1 | go to drawer 1 | go to drawer 2 | open drawer 2 | go to desk 1 | go to drawer 1 | go to desk 1 | take pencil 1 from desk 1 | go to drawer 1 | move pencil 1 to drawer 1
```

## 2. Reflexion retries (ExpeL experience gathering)

A lost practice game is replayed from the start, up to 3 times, with the agent's own reflection on each failed attempt in its prompt; it stops at the first win. Retries change no memory.

**Attempt 1** (retry): WON in 24 steps.

Reflection on the previous failed attempt, given to the agent at the start of this attempt:

> "I repeatedly navigated between desk 1 and drawers without opening the drawer first, then finally
> opened drawer 1 and moved the pencil to it. Instead of opening the drawer before attempting to
> move the pencil, I should have opened drawer 1 immediately upon reaching it to ensure the drawer
> was accessible. I should have opened drawer 1 before moving the pencil to it."

```
go to desk 1 | go to drawer 1 | open drawer 1 | go to desk 1 | take pencil 1 from desk 1 | go to drawer 1 | move pencil 1 to drawer 1 | go to desk 1 | go to drawer 2 | open drawer 2 | go to desk 1 | go to drawer 3 | open drawer 3 | go to desk 1 | go to drawer 1 | go to desk 1 | go to drawer 4 | go to desk 1 | look | go to drawer 5 | go to dresser 1 | take pen 3 from dresser 1 | go to drawer 1 | move pen 3 to drawer 1
```

Retry cost: 27 model calls, 58,978 tokens; retry won: **True**.

## 3. Builder report

Case: **corrected failure**  (first attempt lost, retry won); diagnosis: imperfect rules

- `outcome` the game was LOST; Beta(alpha, beta) of the shown rules ['rule_7', 'rule_3'] updated (won: alpha+1, lost: beta+1); the won game's plan and steps are stored as evidence for the rules.
- `update_rule` rule_7: "When an object must be picked up and placed: search cabinets first, take the object, go to the target, open the target if closed, move the object there."  Validation note: _This game confirmed the agent did not need to open the target container before moving the object. | This game shows the agent searched cabinet 1 first, not drawers, and moved the object directly to th_
- `update_rule` rule_3: "When placing an object in a container, ensure the container is open before attempting to place."  Validation note: _This game shows the desk does not need to be opened before placing the keychain on it. | This game confirms placing on a toilet does not require opening the toilet. | This game confirms placing in a d_
- `pool_won` this won attempt is stored in the hidden failure pool of its kind of task (used to check Anti-Pattern candidates against wins).
- `refine` (MACLA contrastive refinement) rule_7 rewritten from its won and lost games (won/lost counts at refinement [4, 3]): "When an object must be picked up and placed: search drawers and containers first, take the object, go to the target, open the target if closed, move the object there."

## 4. What changed in the manual

- `rule_3` **rule, beta**
  - before: [Special Phenomenon] Beta(3,2) visible=True: When placing an object on a surface, ensure the surface is open before attempting to place.
  - after:  [Special Phenomenon] Beta(3,3) visible=True: When placing an object in a container, ensure the container is open before attempting to place.
- `rule_7` **rule, example, beta**
  - before: [Success Process] Beta(6,3) visible=True: When an object must be picked up and placed: search cabinets first, take the object, go to the target, open the target if closed, move the object there.
  - after:  [Success Process] Beta(6,4) visible=True: When an object must be picked up and placed: search drawers and containers first, take the object, go to the target, open the target if closed, move the object there.
