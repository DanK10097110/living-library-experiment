# Anti-Pattern written: "do not use the command done"

- Run `practice-b`, stream `practice-E-0`, practice game #41. Condition E.
- Goal: **cool some cup and put it in microwave.**   Kind: cool then place
- *What it shows:* A cool task keeps being lost. The pool of never-won games for this kind has 3 games; code finds the invalid command `done` in 4 of 12 lost attempts and in none of the 6 won attempts of this kind, in 2 different tasks. The model only words it: "When cooling an object, do not use the command 'done'".

## 1. The practice game (first attempt)

Outcome: **LOST** in 30 steps (5 invalid).

Rules shown to the agent in this game (from the manual before the game):

- `rule_13` **Success Process** Beta(3,2): When an object must be cooled and placed: search stoveburners first, take the object, go to fridge, open it if closed, cool object with fridge, close fridge, go to target, move object to target.
- `rule_10` **Corrected Error** Beta(19,8): When two objects must be found and placed, search multiple locations before taking each, then move both to the target.

Actions (`!` marks an invalid command):

```
go to cabinet 1 | go to countertop 1 | take mug 1 from countertop 1 | go to fridge 1 | open fridge 1 | cool mug 1 with fridge 1 | close fridge 1 | go to microwave 1 | open microwave 1 | move mug 1 to microwave 1 | close microwave 1 | !done | look | !The task history shows the agent successfully cooled a mug and placed it in the microwave, marking the task as done. However, the current prompt explicitly sets the subgoal to "take the cup from its location" and asks for an action at step 14. Since the cup is currently inside the microwave ( | go to cabinet 1 | go to countertop 1 | go to cabinet 1 | go to cabinet 2 | examine cabinet 2 | examine cabinet 2 | !go to cabinet 3 | go to cabinet 1 | go to countertop 1 | go to cabinet 1 | go to drawer 1 | go to cabinet 2 | !go to cabinet 3 | !go to cabinet 3 | go to drawer 1 | go to cabinet 3
```

## 2. Reflexion retries (ExpeL experience gathering)

A lost practice game is replayed from the start, up to 3 times, with the agent's own reflection on each failed attempt in its prompt; it stops at the first win. Retries change no memory.

**Attempt 1** (retry): lost in 30 steps.

Reflection on the previous failed attempt, given to the agent at the start of this attempt:

> "I successfully cooled the mug and placed it in the microwave, but the task requires taking the
> cup from its location afterward. I should have added a step to open the microwave and remove the
> mug before marking the task as done."

```
go to countertop 1 | take mug 1 from countertop 1 | go to fridge 1 | open fridge 1 | cool mug 1 with fridge 1 | close fridge 1 | go to microwave 1 | open microwave 1 | move mug 1 to microwave 1 | !Currently | !The task is to cool a cup and put it in the microwave. I have cooled the mug and placed it inside the microwave. However, the reflection from the previous attempt indicates that the task requires removing the object from the microwave after placing it, or perhaps the task implies a cycle where the object must be taken | take mug 1 from microwave 1 | close microwave 1 | !move mug 1 to microwave 1 | examine microwave 1 | open microwave 1 | !take mug 1 from microwave 1 | move mug 1 to microwave 1 | take mug 1 from microwave 1 | close microwave 1 | open microwave 1 | go to cabinet 1 | go to microwave 1 | !take mug 1 from microwave 1 | go to fridge 1 | open fridge 1 | cool mug 1 with fridge 1 | close fridge 1 | !move mug 1 to microwave 1 | !open microwave 1
```

**Attempt 2** (retry): lost in 30 steps.

Reflection on the previous failed attempt, given to the agent at the start of this attempt (the list of reflections grows; the model often repeats itself):

> "I cooled the mug and placed it in the microwave, but failed to complete the task because I did
> not remove the mug from the microwave afterward. I should have opened the microwave and taken the
> mug out after placing it inside to fully satisfy the task requirements."

```
go to countertop 1 | take mug 1 from countertop 1 | go to fridge 1 | open fridge 1 | cool mug 1 with fridge 1 | close fridge 1 | go to microwave 1 | open microwave 1 | move mug 1 to microwave 1 | take mug 1 from microwave 1 | move mug 1 to microwave 1 | close microwave 1 | open microwave 1 | close microwave 1 | !The task is to cool a cup and put it in the microwave. I have cooled the mug and placed it inside the microwave (Observation 14 confirms the mug is inside). I just closed the microwave (Action 14). Since the mug is inside the microwave and the task is to put it | open microwave 1 | take mug 1 from microwave 1 | !done | move mug 1 to microwave 1 | close microwave 1 | !The task is to cool a cup and put it in the microwave. The agent has already cooled the mug and placed it inside the microwave (Action 20). The current state is that the microwave is closed. To verify the task is complete or to follow the pattern of ensuring the object is properly placed, | open microwave 1 | take mug 1 from microwave 1 | move mug 1 to microwave 1 | close microwave 1 | open microwave 1 | close microwave 1 | open microwave 1 | take mug 1 from microwave 1 | move mug 1 to microwave 1
```

**Attempt 3** (retry): lost in 30 steps.

Reflection on the previous failed attempt, given to the agent at the start of this attempt (the list of reflections grows; the model often repeats itself):

> "I cooled the mug and placed it in the microwave, but repeatedly closed the microwave without
> verifying the task completion criteria. I should have checked if the task required leaving the mug
> inside or removing it afterward, and if removal was needed, I would have opened the microwave and
> taken the mug out before marking the task as done."

```
go to countertop 1 | take mug 1 from countertop 1 | go to fridge 1 | open fridge 1 | cool mug 1 with fridge 1 | close fridge 1 | go to microwave 1 | open microwave 1 | move mug 1 to microwave 1 | close microwave 1 | open microwave 1 | take mug 1 from microwave 1 | !done | !done | move mug 1 to microwave 1 | close microwave 1 | open microwave 1 | take mug 1 from microwave 1 | go to countertop 1 | !move mug 1 to microwave 1 | go to fridge 1 | open fridge 1 | close fridge 1 | open fridge 1 | !open microwave 1 | cool mug 1 with fridge 1 | !move mug 1 to microwave 1 | !open microwave 1 | !open microwave 1 | !open microwave 1
```

Retry cost: 109 model calls, 325,238 tokens; retry won: **False**.

## 3. Builder report

Case: **failure**  (first attempt lost); diagnosis: imperfect rules

- `outcome` the game was LOST; Beta(alpha, beta) of the shown rules ['rule_13', 'rule_10'] updated (won: alpha+1, lost: beta+1); the won game's plan and steps are stored as evidence for the rules.
- `write_rule` **Unresolved Error** (kind `pick_cool_then_place_in_recep`, verified=False): "When an object must be cooled and placed in a container, open the container and take the object out after placing it inside if the task requires removal."  Example: _The agent failed because it placed the mug in the microwave but did not take it out before marking the task done._
- `pool_game` this never-won game (4 attempts: the first and each failed retry) is pooled by kind of task (`pick_cool_then_place_in_recep`) for Anti-Pattern mining.
- `write_rule` **Anti-Pattern** (kind `pick_cool_then_place_in_recep`, verified=True): "When cooling an object, do not use the command "done"."  Example: _"done" answers "Nothing happens."_  Pattern: invalid `done` seen in 2 of 3 never-won tasks, 4 of 12 lost attempts, 6 won attempts checked (none contained it).
- `refine` (MACLA contrastive refinement) rule_10 rewritten from its won and lost games (won/lost counts at refinement [17, 8]): "When an object must be cooled and placed, search kitchen areas first, cool with fridge if closed, then move to target."

Log lines the Builder step produced (verbatim), with what they mean:

- `rule_22 anti-pattern written from 2 of 3 lost tasks`
  - Anti-Pattern mined by code from pooled never-won games and worded by the model (see the rule below).

## 4. What changed in the manual

- `rule_10` **rule, beta**
  - before: [Corrected Error] Beta(19,8) visible=True: When two objects must be found and placed, search multiple locations before taking each, then move both to the target.
  - after:  [Corrected Error] Beta(19,9) visible=True: When an object must be cooled and placed, search kitchen areas first, cool with fridge if closed, then move to target.
- `rule_13` **beta**
  - before: [Success Process] Beta(3,2) visible=True: When an object must be cooled and placed: search stoveburners first, take the object, go to fridge, open it if closed, cool object with fridge, close fridge, go to target, move object to target.
  - after:  [Success Process] Beta(3,3) visible=True: When an object must be cooled and placed: search stoveburners first, take the object, go to fridge, open it if closed, cool object with fridge, close fridge, go to target, move object to target.
- `rule_21` **NEW**
  - after:  [Unresolved Error] Beta(1,1) visible=False: When an object must be cooled and placed in a container, open the container and take the object out after placing it inside if the task requires removal.
- `rule_22` **NEW**
  - after:  [Anti-Pattern] Beta(1,1) visible=True: When cooling an object, do not use the command "done".
