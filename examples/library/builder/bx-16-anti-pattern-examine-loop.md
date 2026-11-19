# Anti-Pattern written from 2 of 3 lost tasks (examine loop)

- Run `practice-e`, stream `practice-E-0`, practice game #27. Condition E.
- Goal: **put some pen on drawer.**   Kind: pick and place
- *What it shows:* A pick-and-place task is lost, and with the pooled earlier lost games a repeated-command pattern (`examine` over and over) appears in 2 of 3 never-won tasks; "rule_17 anti-pattern written from 2 of 3 lost tasks".

## 1. The practice game (first attempt)

Outcome: **LOST** in 30 steps (0 invalid).

Rules shown to the agent in this game (from the manual before the game):

- `rule_4` **Success Process** Beta(6,3): When an object must be placed in a container: search the area for the object, take it, go to the container, open it if closed, move the object to the container.

Actions (`!` marks an invalid command):

```
go to desk 1 | go to drawer 1 | go to desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | go to drawer 1 | open drawer 1 | go to desk 1 | go to drawer 1 | go to desk 1 | take pencil 1 from desk 1 | go to drawer 1 | move pencil 1 to drawer 1 | go to desk 1 | go to drawer 1 | go to desk 1 | go to drawer 1 | go to desk 1 | go to drawer 1 | go to desk 1 | go to drawer 2 | open drawer 2 | go to drawer 1
```

## 2. Reflexion retries (ExpeL experience gathering)

A lost practice game is replayed from the start, up to 3 times, with the agent's own reflection on each failed attempt in its prompt; it stops at the first win. Retries change no memory.

**Attempt 1** (retry): lost in 30 steps.

Reflection on the previous failed attempt, given to the agent at the start of this attempt:

> "I repeatedly examined desk 1 without taking action, then moved a pencil to drawer 1 instead of a
> pen. I should have identified and taken a pen from desk 1 first, then placed it on the drawer
> surface rather than inside the drawer."

```
go to desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | go to drawer 1 | go to desk 1
```

**Attempt 2** (retry): lost in 30 steps.

Reflection on the previous failed attempt, given to the agent at the start of this attempt (the list of reflections grows; the model often repeats itself):

> "I repeatedly examined desk 1 without taking action, then moved a pencil to drawer 1 instead of a
> pen. I should have identified and taken a pen from desk 1 first, then placed it on the drawer
> surface rather than inside the drawer."

```
go to desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | go to drawer 1 | go to desk 1
```

**Attempt 3** (retry): lost in 30 steps.

Reflection on the previous failed attempt, given to the agent at the start of this attempt (the list of reflections grows; the model often repeats itself):

> "I repeatedly examined desk 1 without taking action, then moved a pencil to drawer 1 instead of a
> pen. I should have identified and taken a pen from desk 1 first, then placed it on the drawer
> surface rather than inside the drawer."

```
go to desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1 | examine desk 1
```

Retry cost: 103 model calls, 243,331 tokens; retry won: **False**.

## 3. Builder report

Case: **failure**  (first attempt lost); diagnosis: imperfect rules

- `outcome` the game was LOST; Beta(alpha, beta) of the shown rules ['rule_4'] updated (won: alpha+1, lost: beta+1); the won game's plan and steps are stored as evidence for the rules.
- `update_rule` rule_4  Validation note: _Confirmed: object found on countertop, container was open, move command succeeded. | Confirmed: object found on cabinet, target was toilet, move command succeeded. | Confirmed: agent repeatedly examin_
- `pool_game` this never-won game (4 attempts: the first and each failed retry) is pooled by kind of task (`pick_and_place_simple`) for Anti-Pattern mining.
- `write_rule` **Anti-Pattern** (kind `pick_and_place_simple`, verified=True): "When examining an appliance, do not issue the same "examine" command again and again."  Example: _"examine desk", again and again_  Pattern: repeat `` seen in 2 of 3 never-won tasks, 7 of 12 lost attempts, 7 won attempts checked (none contained it).
- `refine` (MACLA contrastive refinement) rule_4 rewritten from its won and lost games (won/lost counts at refinement [4, 3]): "When an object must be placed on a target: search the area first, take the object, go to the target, open the target if closed, move the object to the target."

Log lines the Builder step produced (verbatim), with what they mean:

- `rule_4 keeps its text (a lost game may not rewrite a rule the agent sees)`
  - Guard: a lost game may not rewrite a rule the agent sees (only a validation note is added).
- `rule_17 anti-pattern written from 2 of 3 lost tasks`
  - Anti-Pattern mined by code from pooled never-won games and worded by the model (see the rule below).

## 4. What changed in the manual

- `rule_4` **rule, beta**
  - before: [Success Process] Beta(6,3) visible=True: When an object must be placed in a container: search the area for the object, take it, go to the container, open it if closed, move the object to the container.
  - after:  [Success Process] Beta(6,4) visible=True: When an object must be placed on a target: search the area first, take the object, go to the target, open the target if closed, move the object to the target.
- `rule_18` **NEW**
  - after:  [Anti-Pattern] Beta(1,1) visible=True: When examining an appliance, do not issue the same "examine" command again and again.
