# Rejected: a Success Process that is too long

- Run `practice-d`, stream `practice-E-0`, practice game #38. Condition E.
- Goal: **examine the pen with the desklamp.**   Kind: look at object under a lamp
- *What it shows:* A Success Process of 46 words (limit 45) is rejected.

## 1. The practice game (first attempt)

Outcome: **LOST** in 30 steps (16 invalid).

Rules shown to the agent in this game (from the manual before the game):

- `rule_22` **Corrected Error** Beta(4,4): When placing an object on a bed, use 'move <object> to bed' after taking it, not 'go to bed' then 'take' again.

Actions (`!` marks an invalid command):

```
go to desk 1 | !go to desk 1 | take pen 2 from desk 1 | !go to desk 1 | move pen 2 to desk 1 | !take desklamp from desk 1 | look | !take desklamp from desk 1 | !take desklamp from desk 1 | !take desklamp from desk 1 | !take desklamp from desk 1 | !take desklamp from desk 1 | examine desk 1 | !take desklamp from desk 1 | !drop pen 2 | !take desklamp from desk 1 | !take desklamp from desk 1 | !take desklamp from desk 1 | take pen 2 from desk 1 | !The reasoning concluded that the agent has the pen and needs to examine it with the desklamp. The available actions include 'examine pen 2'. Given the previous failures to take the desklamp and the current state of holding the | examine pen 2 | move pen 2 to desk 1 | look | inventory | take pen 2 from desk 1 | move pen 2 to desk 1 | look | !go to desk 1 | !go to desk 1 | go to shelf 1
```

## 2. Reflexion retries (ExpeL experience gathering)

A lost practice game is replayed from the start, up to 3 times, with the agent's own reflection on each failed attempt in its prompt; it stops at the first win. Retries change no memory.

**Attempt 1** (retry): WON in 13 steps.

Reflection on the previous failed attempt, given to the agent at the start of this attempt:

> "I repeatedly failed to take the desklamp because it was not visible on desk 1 despite multiple
> attempts; I should have examined the desk more thoroughly or checked other locations for the
> desklamp before trying to take it. I also unnecessarily moved the pen back and forth instead of
> directly examining it with the desklamp once both were located. A better approach would be to
> first locate and take"

```
go to drawer 1 | go to desk 1 | examine desk 1 | take pen 2 from desk 1 | examine desk 1 | !go to desk 1 | examine desk 1 | examine desk 1 | go to drawer 1 | open drawer 1 | go to desk 1 | go to dresser 1 | use desklamp 1
```

Retry cost: 15 model calls, 35,483 tokens; retry won: **True**.

## 3. Builder report

Case: **corrected failure**  (first attempt lost, retry won); diagnosis: imperfect rules

- `outcome` the game was LOST; Beta(alpha, beta) of the shown rules ['rule_22'] updated (won: alpha+1, lost: beta+1); the won game's plan and steps are stored as evidence for the rules.
- `write_rule` **Corrected Error** (kind `look_at_obj_in_light`, verified=True): "When an object must be examined with a light source and the source is not visible on the target surface, examine the target and check other locations (drawers, dressers) for the light source."  Example: _examine desk, check drawer/dresser for desklamp, use desklamp_
- `pool_won` this won attempt is stored in the hidden failure pool of its kind of task (used to check Anti-Pattern candidates against wins).

Log lines the Builder step produced (verbatim), with what they mean:

- `rejected Success Process text, too long (46 words > 45): When an object must be examined with a light source: examine the target surface `
  - Code check: rule text has a word limit (Success Process 45 words, others shorter).

## 4. What changed in the manual

- `rule_22` **beta**
  - before: [Corrected Error] Beta(4,4) visible=True: When placing an object on a bed, use 'move <object> to bed' after taking it, not 'go to bed' then 'take' again.
  - after:  [Corrected Error] Beta(4,5) visible=True: When placing an object on a bed, use 'move <object> to bed' after taking it, not 'go to bed' then 'take' again.
- `rule_23` **NEW**
  - after:  [Corrected Error] Beta(1,1) visible=True: When an object must be examined with a light source and the source is not visible on the target surface, examine the target and check other locations (drawers, dressers) for the light source.
