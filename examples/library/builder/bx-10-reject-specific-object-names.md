# Rejected: rule names specific objects after one rewrite attempt

- Run `practice-e`, stream `practice-E-0`, practice game #4. Condition E.
- Goal: **put a hot mug in coffeemachine.**   Kind: heat then place
- *What it shows:* A heat task: the Unresolved Error text names "kettle". The check "names specific objects or rooms" gives the Builder ONE rewrite ("use the object / the target"); the rewrite was still specific and the rule was rejected: `rejected Unresolved Error text, names specific objects or rooms (kettle)`.

## 1. The practice game (first attempt)

Outcome: **LOST** in 30 steps (6 invalid).

Rules shown to the agent in this game (from the manual before the game):

- none (no rule of this kind existed yet)

Actions (`!` marks an invalid command):

```
go to drawer 1 | go to countertop 1 | go to stoveburner 1 | go to countertop 1 | take mug 1 from countertop 1 | go to stoveburner 1 | !place mug 1 on stoveburner 1 | examine stoveburner 1 | examine stoveburner 1 | go to stoveburner 2 | go to stoveburner 1 | examine stoveburner 1 | examine stoveburner 1 | examine stoveburner 1 | examine mug 1 | !go to stoveburner 1 | examine stoveburner 1 | !go to stoveburner 1 | examine mug 1 | go to sinkbasin 1 | clean mug 1 with sinkbasin 1 | go to stoveburner 1 | examine stoveburner 1 | !heat mug 1 with stoveburner 1 | !heat mug 1 with stoveburner 2 | examine mug 1 | examine mug 1 | !go to stoveburner 3 | examine stoveburner 3 | go to microwave 1
```

## 2. Reflexion retries (ExpeL experience gathering)

A lost practice game is replayed from the start, up to 3 times, with the agent's own reflection on each failed attempt in its prompt; it stops at the first win. Retries change no memory.

**Attempt 1** (retry): lost in 30 steps.

Reflection on the previous failed attempt, given to the agent at the start of this attempt:

> "I failed because I tried to place the mug directly on the stoveburner without heating the kettle
> first, and later attempted to heat the mug directly on the stoveburner which was invalid. Instead,
> I should have heated the kettle on the stoveburner to get hot water, then poured it into the mug
> to make it hot, and finally placed the hot mug in the coffeemachine."

```
look | go to countertop 1 | go to fridge 1 | go to countertop 1 | go to fridge 1 | go to stoveburner 1 | take kettle 1 from stoveburner 1 | move kettle 1 to stoveburner 1 | examine stoveburner 1 | examine stoveburner 1 | !turn on stoveburner 1 | examine stoveburner 1 | examine stoveburner 1 | examine stoveburner 1 | examine stoveburner 1 | take kettle 1 from stoveburner 1 | move kettle 1 to stoveburner 1 | take kettle 1 from stoveburner 1 | move kettle 1 to stoveburner 1 | !turn on stoveburner 1 | !move kettle 1 to stoveburner 1 | !move kettle 1 to stoveburner 1 | !move kettle 1 to stoveburner 1 | !place kettle 1 on stoveburner 1 | examine stoveburner 1 | !turn on stoveburner 1 | !place kettle 1 on stoveburner 1 | !place kettle 1 on stoveburner 1 | !place kettle 1 on stoveburner 1 | !turn on stoveburner 1
```

**Attempt 2** (retry): lost in 30 steps.

Reflection on the previous failed attempt, given to the agent at the start of this attempt (the list of reflections grows; the model often repeats itself):

> "I failed because I repeatedly attempted to turn on the stoveburner and move the kettle without
> success, likely due to incorrect action sequences or missing prerequisites like opening the fridge
> first. Instead, I should have first opened the fridge 1 to retrieve the mug 1, then successfully
> heated the kettle 1 on the stoveburner 1, poured hot water into the mug 1, and finally placed the
> hot mug 1 i"

```
go to fridge 1 | open fridge 1 | close fridge 1 | !go to diningtable 1 | !go to diningtable 1 | !go to diningtable 1 | !go to diningtable 1 | !go to diningtable 1 | !go to diningtable 1 | !go to diningtable 1 | !go to diningtable 1 | open fridge 1 | inventory | take cup 2 from fridge 1 | go to microwave 1 | open microwave 1 | go to fridge 1 | go to cabinet 1 | open cabinet 1 | !go to diningtable 1 | !go to diningtable 1 | !go to diningtable 1 | go to fridge 1 | move cup 2 to fridge 1 | !take mug 1 from fridge 1 | !take mug 1 from fridge 1 | !take mug 1 from fridge 1 | close fridge 1 | go to stoveburner 1 | take kettle 1 from stoveburner 1
```

**Attempt 3** (retry): lost in 30 steps.

Reflection on the previous failed attempt, given to the agent at the start of this attempt (the list of reflections grows; the model often repeats itself):

> "I failed because I repeatedly attempted invalid actions like moving the cup to the fridge and
> trying to take the mug from the fridge without first locating it, and I never successfully heated
> the kettle to make the mug hot. Instead, I should have first opened the fridge 1 to retrieve the
> mug 1, then opened the stoveburner 1 and heated the kettle 1, poured hot water into the mug 1, and
> finally plac"

```
go to fridge 1 | open fridge 1 | close fridge 1 | open fridge 1 | close fridge 1 | go to countertop 1 | go to fridge 1 | open fridge 1 | go to countertop 1 | take mug 1 from countertop 1 | go to stoveburner 1 | examine stoveburner 1 | examine stoveburner 1 | !turn on stoveburner 1 | examine stoveburner 1 | !turn on stoveburner 1 | !place kettle 1 on stoveburner 1 | !turn on stoveburner 1 | !place kettle 1 on stoveburner 1 | inventory | !place kettle 1 on stoveburner 1 | !place kettle 1 on stoveburner 1 | !place kettle 1 on stoveburner 1 | examine stoveburner 1 | examine stoveburner 1 | !turn on stoveburner 1 | !turn on stoveburner 1 | examine stoveburner 1 | !wait | !wait
```

Retry cost: 102 model calls, 268,316 tokens; retry won: **False**.

## 3. Builder report

Case: **failure**  (first attempt lost); diagnosis: imperfect rules

- `outcome` the game was LOST; Beta(alpha, beta) of the shown rules [] updated (won: alpha+1, lost: beta+1); the won game's plan and steps are stored as evidence for the rules.
- `pool_game` this never-won game (4 attempts: the first and each failed retry) is pooled by kind of task (`pick_heat_then_place_in_recep`) for Anti-Pattern mining.

Log lines the Builder step produced (verbatim), with what they mean:

- `rejected Unresolved Error text, names specific objects or rooms (kettle): When heating a container to make it hot, never place the target directly on the `
  - Code check: a rule must not name a portable object kind or a room. The Builder got ONE rewrite ("use the object / the target"); the rewrite was still specific, so the rule was rejected.

## 4. What changed in the manual

Nothing visible changed (no rule added or edited).

