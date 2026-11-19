# A lost game cannot rewrite a rule the agent sees

- Run `study`, stream `practice-E-0`, practice game #19. Condition E.
- Goal: **cool some plate and put it in cabinet.**   Kind: cool then place
- *What it shows:* A cool task loses after 3 retries. The Builder tries to update rule_13 (visible); the code keeps the confirmed text and only the validation note is added: "rule_13 keeps its text (a lost game may not rewrite a rule the agent sees)".

## 1. The practice game (first attempt)

Outcome: **LOST** in 30 steps (0 invalid).

Rules shown to the agent in this game (from the manual before the game):

- `rule_13` **Success Process** Beta(1,2): When the object must be cooled and placed in the target: search stoveburners and countertops first, take the object, cool it with the fridge, open the target cabinet if closed, move the object there.
- `rule_12` **Corrected Error** Beta(1,2): When an object must be found and cooled, search stoveburners and countertops first instead of opening cabinets.

Actions (`!` marks an invalid command):

```
go to countertop 1 | go to countertop 2 | go to countertop 3 | go to cabinet 1 | open cabinet 1 | go to countertop 1 | go to countertop 2 | go to countertop 3 | go to cabinet 1 | go to cabinet 2 | open cabinet 2 | go to cabinet 3 | open cabinet 3 | go to countertop 1 | go to countertop 2 | go to countertop 3 | go to cabinet 1 | go to countertop 1 | go to countertop 3 | go to countertop 1 | go to countertop 3 | go to countertop 2 | go to countertop 3 | go to countertop 1 | go to countertop 2 | go to countertop 1 | go to drawer 1 | go to countertop 3 | go to countertop 1 | go to drawer 1
```

## 2. Reflexion retries (ExpeL experience gathering)

A lost practice game is replayed from the start, up to 3 times, with the agent's own reflection on each failed attempt in its prompt; it stops at the first win. Retries change no memory.

**Attempt 1** (retry): lost in 30 steps.

Reflection on the previous failed attempt, given to the agent at the start of this attempt:

> "I failed because I never identified or picked up a plate to cool, instead repeatedly moving
> between countertops and cabinets without locating the required object. I should have first
> searched all countertops for a plate, picked it up, used the cooling action, and then placed it in
> the cabinet."

```
go to countertop 1 | go to countertop 2 | go to countertop 3 | go to drawer 1 | open drawer 1 | go to drawer 2 | open drawer 2 | go to countertop 3 | go to countertop 2 | go to drawer 3 | examine drawer 3 | go to countertop 1 | go to countertop 2 | !go to drawer 4 | go to countertop 1 | go to countertop 2 | go to countertop 1 | examine countertop 1 | go to countertop 3 | go to countertop 1 | go to cabinet 1 | go to drawer 1 | go to countertop 1 | go to countertop 2 | go to countertop 3 | go to drawer 1 | go to countertop 2 | go to countertop 1 | go to countertop 2 | go to countertop 1
```

**Attempt 2** (retry): lost in 30 steps.

Reflection on the previous failed attempt, given to the agent at the start of this attempt (the list of reflections grows; the model often repeats itself):

> "I failed because I never identified or picked up a plate to cool, instead repeatedly moving
> between countertops and cabinets without locating the required object. I should have first
> searched all countertops for a plate, picked it up, used the cooling action, and then placed it in
> the cabinet."

```
go to countertop 1 | go to countertop 2 | go to countertop 3 | go to cabinet 1 | open cabinet 1 | go to countertop 1 | go to countertop 2 | go to countertop 3 | go to countertop 1 | go to countertop 2 | go to countertop 3 | go to cabinet 1 | go to countertop 1 | go to countertop 2 | go to drawer 1 | open drawer 1 | go to drawer 2 | open drawer 2 | go to countertop 2 | go to cabinet 1 | go to countertop 1 | go to countertop 2 | go to countertop 3 | go to countertop 1 | go to countertop 2 | go to countertop 3 | go to cabinet 1 | go to countertop 1 | go to countertop 2 | go to drawer 1
```

**Attempt 3** (retry): lost in 30 steps.

Reflection on the previous failed attempt, given to the agent at the start of this attempt (the list of reflections grows; the model often repeats itself):

> "I failed because I never identified or picked up a plate to cool, instead repeatedly moving
> between countertops and cabinets without locating the required object. I should have first
> searched all countertops for a plate, picked it up, used the cooling action, and then placed it in
> the cabinet."

```
go to countertop 1 | go to countertop 2 | go to countertop 3 | go to cabinet 1 | open cabinet 1 | go to countertop 2 | go to countertop 3 | !go to diningtable 1 | !go to diningtable 1 | !go to diningtable 1 | go to countertop 1 | go to countertop 2 | !go to diningtable 1 | !go to diningtable 1 | go to countertop 3 | go to drawer 1 | go to countertop 1 | go to cabinet 1 | go to countertop 2 | examine countertop 2 | go to countertop 3 | go to cabinet 1 | go to countertop 1 | go to countertop 2 | examine countertop 2 | go to cabinet 1 | go to countertop 3 | go to countertop 1 | go to drawer 1 | go to countertop 1
```

Retry cost: 104 model calls, 313,897 tokens; retry won: **False**.

## 3. Builder report

Case: **failure**  (first attempt lost); diagnosis: imperfect rules

- `outcome` the game was LOST; Beta(alpha, beta) of the shown rules ['rule_13', 'rule_12'] updated (won: alpha+1, lost: beta+1); the won game's plan and steps are stored as evidence for the rules.
- `update_rule` rule_13  Validation note: _The agent failed because it never searched countertops for a plate to cool, instead repeatedly moving between countertops and cabinets without locating the required object._
- `pool_game` this never-won game (4 attempts: the first and each failed retry) is pooled by kind of task (`pick_cool_then_place_in_recep`) for Anti-Pattern mining.

Log lines the Builder step produced (verbatim), with what they mean:

- `rule_13 keeps its text (a lost game may not rewrite a rule the agent sees)`
  - Guard: a lost game may not rewrite a rule the agent sees (only a validation note is added).

## 4. What changed in the manual

- `rule_12` **beta**
  - before: [Corrected Error] Beta(1,2) visible=True: When an object must be found and cooled, search stoveburners and countertops first instead of opening cabinets.
  - after:  [Corrected Error] Beta(1,3) visible=True: When an object must be found and cooled, search stoveburners and countertops first instead of opening cabinets.
- `rule_13` **beta**
  - before: [Success Process] Beta(1,2) visible=True: When the object must be cooled and placed in the target: search stoveburners and countertops first, take the object, cool it with the fridge, open the target cabinet if closed, move the object there.
  - after:  [Success Process] Beta(1,3) visible=True: When the object must be cooled and placed in the target: search stoveburners and countertops first, take the object, cool it with the fridge, open the target cabinet if closed, move the object there.
