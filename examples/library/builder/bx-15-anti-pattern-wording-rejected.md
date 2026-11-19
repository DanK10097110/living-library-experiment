# Anti-Pattern: model wording rejected twice, then accepted

- Run `study`, stream `practice-E-0`, practice game #20. Condition E.
- Goal: **put a hot potato in diningtable.**   Kind: heat then place
- *What it shows:* Heat task never won. Code mines two patterns (a repeated `wait` and a repeated `examine`). The model's wording for the first ("When waiting for an object to cool, do not use the command wait") is rejected twice because it mentions "cool", a word the measured pattern does not contain. The `examine` pattern is accepted as rule_16 and stays visible.

## 1. The practice game (first attempt)

Outcome: **LOST** in 30 steps (5 invalid).

Rules shown to the agent in this game (from the manual before the game):

- none (no rule of this kind existed yet)

Actions (`!` marks an invalid command):

```
go to cabinet 1 | go to fridge 1 | go to countertop 1 | go to fridge 1 | go to cabinet 1 | go to fridge 1 | open fridge 1 | go to countertop 1 | go to countertop 2 | go to stoveburner 1 | go to countertop 2 | take potato 3 from countertop 2 | go to stoveburner 1 | !I am holding the potato 3 and am currently at stoveburner 1. To heat the potato as required by my subgoal, I need to place it on the stoveburner. Since I am already at the stoveburner, I should examine it or attempt to place the potato on it. | examine stoveburner 1 | !place potato 3 on stoveburner 1 | go to microwave 1 | open microwave 1 | move potato 3 to microwave 1 | close microwave 1 | open microwave 1 | !open microwave 1 | take potato 3 from microwave 1 | !move potato 3 to diningtable 1 | !go to microwave 1 | examine potato 3 | move potato 3 to microwave 1 | close microwave 1 | open microwave 1 | close microwave 1
```

## 2. Reflexion retries (ExpeL experience gathering)

A lost practice game is replayed from the start, up to 3 times, with the agent's own reflection on each failed attempt in its prompt; it stops at the first win. Retries change no memory.

**Attempt 1** (retry): lost in 30 steps.

Reflection on the previous failed attempt, given to the agent at the start of this attempt:

> "I failed because I repeatedly moved the potato back and forth between the microwave and
> countertop without actually heating it or placing it on the dining table. Instead, I should have
> placed the potato on the stoveburner 1 to heat it, then directly moved it to diningtable 1 once it
> was hot."

```
go to cabinet 1 | go to fridge 1 | open fridge 1 | go to countertop 1 | go to countertop 2 | go to stoveburner 1 | !move potato 3 to stoveburner 1 | examine stoveburner 1 | go to countertop 2 | take potato 3 from countertop 2 | go to stoveburner 1 | !move potato 3 to stoveburner 1 | !move potato 3 to stoveburner 1 | examine stoveburner 1 | examine stoveburner 1 | examine stoveburner 1 | go to microwave 1 | open microwave 1 | move potato 3 to microwave 1 | close microwave 1 | open microwave 1 | take potato 3 from microwave 1 | !move potato 3 to stoveburner 1 | !heat potato 3 with stoveburner 1 | move potato 3 to microwave 1 | take potato 3 from microwave 1 | !move potato 3 to stoveburner 1 | !heat potato 3 with stoveburner 1 | heat potato 3 with microwave 1 | close microwave 1
```

**Attempt 2** (retry): lost in 30 steps.

Reflection on the previous failed attempt, given to the agent at the start of this attempt (the list of reflections grows; the model often repeats itself):

> "I failed because I repeatedly moved the potato between the microwave and countertop without
> successfully heating it or placing it on the dining table. Instead, I should have placed the
> potato on stoveburner 1 to heat it, then directly moved it to diningtable 1 once it was hot."

```
go to cabinet 1 | go to stoveburner 1 | go to fridge 1 | open fridge 1 | go to cabinet 1 | open cabinet 1 | go to fridge 1 | go to countertop 1 | go to cabinet 2 | open cabinet 2 | go to fridge 1 | go to countertop 1 | go to diningtable 1 | take potato 1 from diningtable 1 | go to stoveburner 1 | !put potato 1 on stoveburner 1 | !wait | !wait | go to diningtable 1 | move potato 1 to diningtable 1 | go to stoveburner 1 | !wait | examine stoveburner 1 | go to microwave 1 | go to stoveburner 1 | go to diningtable 1 | !move potato 1 to stoveburner 1 | !wait | !move potato 1 to stoveburner 1 | take potato 1 from diningtable 1
```

**Attempt 3** (retry): lost in 30 steps.

Reflection on the previous failed attempt, given to the agent at the start of this attempt (the list of reflections grows; the model often repeats itself):

> "I failed because I repeatedly moved the potato between the diningtable and stoveburner without
> successfully heating it first, and the stoveburner showed nothing indicating it wasn't hot.
> Instead, I should have placed the potato on stoveburner 1, waited for it to heat up (checking if
> it became hot), and then moved it to diningtable 1 to complete the task."

```
go to fridge 1 | open fridge 1 | go to countertop 1 | go to fridge 1 | go to countertop 1 | go to fridge 1 | go to countertop 1 | go to diningtable 1 | take potato 1 from diningtable 1 | go to stoveburner 1 | !put potato 1 on stoveburner 1 | !wait | !wait | examine stoveburner 1 | go to microwave 1 | open microwave 1 | move potato 1 to microwave 1 | close microwave 1 | open microwave 1 | close microwave 1 | go to stoveburner 1 | !wait | !place potato 1 on stoveburner 1 | !wait | !wait | examine stoveburner 1 | !wait | go to microwave 1 | go to stoveburner 1 | !wait
```

Retry cost: 103 model calls, 290,566 tokens; retry won: **False**.

## 3. Builder report

Case: **failure**  (first attempt lost); diagnosis: imperfect rules

- `outcome` the game was LOST; Beta(alpha, beta) of the shown rules [] updated (won: alpha+1, lost: beta+1); the won game's plan and steps are stored as evidence for the rules.
- `write_rule` **Special Phenomenon** (kind `pick_heat_then_place_in_recep`, verified=False): "When heating an object on a stoveburner, examine it first to confirm it is hot before moving it to the target."  Example: _The agent failed because it placed the potato on stoveburner 1 without confirming it was hot, then switched to the microwave._
- `pool_game` this never-won game (4 attempts: the first and each failed retry) is pooled by kind of task (`pick_heat_then_place_in_recep`) for Anti-Pattern mining.
- `write_rule` **Anti-Pattern** (kind `pick_heat_then_place_in_recep`, verified=True): "When examining an appliance, do not issue the same "examine" command again and again."  Example: _"examine stoveburner", again and again_  Pattern: repeat `` seen in 2 of 2 never-won tasks, 4 of 8 lost attempts, 0 won attempts checked (none contained it).

Log lines the Builder step produced (verbatim), with what they mean:

- `rule_15 is a hidden Builder note until a won game confirms it`
  - A rule written from a lost game is an unconfirmed guess: stored, but never shown to the agent yet.
- `a failure may not write a Success Process rule`
  - Guard: a lost game cannot write a recipe (Success Process).
- `anti-pattern rejected 'When waiting for an object to cool, do not use the command "wait".': names ['cool'] which the measured pattern does not contain`
  - The model worded the measured pattern, but code rejected the wording (it names something the pattern does not contain).
- `anti-pattern rejected 'When waiting for an object to cool, do not use the command "wait".': names ['cool'] which the measured pattern does not contain`
  - The model worded the measured pattern, but code rejected the wording (it names something the pattern does not contain).
- `rule_16 anti-pattern written from 2 of 2 lost tasks`
  - Anti-Pattern mined by code from pooled never-won games and worded by the model (see the rule below).

## 4. What changed in the manual

- `rule_15` **NEW**
  - after:  [Special Phenomenon] Beta(1,1) visible=False: When heating an object on a stoveburner, examine it first to confirm it is hot before moving it to the target.
- `rule_16` **NEW**
  - after:  [Anti-Pattern] Beta(1,1) visible=True: When examining an appliance, do not issue the same "examine" command again and again.
