# Rejected: an Unresolved Error that lists steps

- Run `practice-d`, stream `practice-E-0`, practice game #6. Condition E.
- Goal: **clean some plate and put it in microwave.**   Kind: clean then place
- *What it shows:* Only a Success Process may list steps; the Builder wrote an Unresolved Error with a step list and code rejects it ("lists steps (only a Success Process may)").

## 1. The practice game (first attempt)

Outcome: **LOST** in 30 steps (1 invalid).

Rules shown to the agent in this game (from the manual before the game):

- none (no rule of this kind existed yet)

Actions (`!` marks an invalid command):

```
go to countertop 1 | go to diningtable 1 | go to cabinet 1 | open cabinet 1 | go to fridge 1 | open fridge 1 | go to cabinet 1 | go to diningtable 1 | go to cabinet 2 | open cabinet 2 | go to drawer 1 | open drawer 1 | go to countertop 1 | go to sinkbasin 1 | go to diningtable 1 | go to fridge 1 | go to garbagecan 1 | go to diningtable 1 | go to cabinet 1 | go to microwave 1 | go to cabinet 1 | go to fridge 1 | go to countertop 1 | !go to countertop 1 | go to cabinet 1 | go to fridge 1 | go to garbagecan 1 | go to diningtable 1 | go to sinkbasin 1 | go to diningtable 1
```

## 2. Reflexion retries (ExpeL experience gathering)

A lost practice game is replayed from the start, up to 3 times, with the agent's own reflection on each failed attempt in its prompt; it stops at the first win. Retries change no memory.

**Attempt 1** (retry): lost in 30 steps.

Reflection on the previous failed attempt, given to the agent at the start of this attempt:

> "I failed because I never located or cleaned a plate, instead repeatedly checking cabinets,
> drawers, and the fridge without finding a plate to clean. I should have systematically searched
> the diningtable and countertop for a plate, cleaned it at the sinkbasin, and then placed it in the
> microwave 1."

```
go to diningtable 1 | go to countertop 1 | go to diningtable 1 | go to fridge 1 | open fridge 1 | go to diningtable 1 | go to cabinet 1 | open cabinet 1 | go to drawer 1 | open drawer 1 | go to drawer 2 | open drawer 2 | go to diningtable 1 | go to countertop 1 | go to diningtable 1 | go to sinkbasin 1 | go to fridge 1 | take bowl 1 from fridge 1 | go to diningtable 1 | go to countertop 1 | go to cabinet 1 | go to cabinet 2 | open cabinet 2 | go to diningtable 1 | go to countertop 1 | go to diningtable 1 | go to cabinet 3 | open cabinet 3 | go to diningtable 1 | go to fridge 1
```

**Attempt 2** (retry): lost in 30 steps.

Reflection on the previous failed attempt, given to the agent at the start of this attempt (the list of reflections grows; the model often repeats itself):

> "I failed because I never located or cleaned a plate, instead repeatedly checking cabinets,
> drawers, and the fridge without finding a plate to clean. I should have systematically searched
> the diningtable and countertop for a plate, cleaned it at the sinkbasin, and then placed it in the
> microwave 1."

```
go to diningtable 1 | go to countertop 1 | go to fridge 1 | go to cabinet 1 | open cabinet 1 | go to sinkbasin 1 | go to diningtable 1 | go to drawer 1 | go to diningtable 1 | go to garbagecan 1 | go to cabinet 1 | go to diningtable 1 | go to countertop 1 | go to fridge 1 | open fridge 1 | close fridge 1 | go to cabinet 1 | go to sinkbasin 1 | go to diningtable 1 | go to cabinet 2 | open cabinet 2 | close cabinet 2 | go to countertop 1 | go to drawer 1 | open drawer 1 | close drawer 1 | go to diningtable 1 | go to fridge 1 | open fridge 1 | close fridge 1
```

**Attempt 3** (retry): lost in 30 steps.

Reflection on the previous failed attempt, given to the agent at the start of this attempt (the list of reflections grows; the model often repeats itself):

> "I failed because I repeatedly checked cabinets, drawers, and the fridge without finding a plate,
> and never attempted to clean anything at the sinkbasin. I should have immediately searched the
> diningtable and countertop for a plate, then cleaned it at the sinkbasin before placing it in the
> microwave 1."

```
go to diningtable 1 | go to countertop 1 | go to diningtable 1 | go to fridge 1 | open fridge 1 | go to diningtable 1 | go to cabinet 1 | open cabinet 1 | go to drawer 1 | open drawer 1 | go to drawer 2 | go to diningtable 1 | go to countertop 1 | go to diningtable 1 | go to garbagecan 1 | go to diningtable 1 | go to cabinet 2 | go to fridge 1 | go to diningtable 1 | go to cabinet 1 | go to sinkbasin 1 | go to diningtable 1 | go to countertop 1 | go to sinkbasin 1 | go to diningtable 1 | go to countertop 1 | go to diningtable 1 | go to countertop 1 | go to diningtable 1 | go to cabinet 1
```

Retry cost: 102 model calls, 293,954 tokens; retry won: **False**.

## 3. Builder report

Case: **failure**  (first attempt lost); diagnosis: imperfect rules

- `outcome` the game was LOST; Beta(alpha, beta) of the shown rules [] updated (won: alpha+1, lost: beta+1); the won game's plan and steps are stored as evidence for the rules.
- `pool_game` this never-won game (4 attempts: the first and each failed retry) is pooled by kind of task (`pick_clean_then_place_in_recep`) for Anti-Pattern mining.

Log lines the Builder step produced (verbatim), with what they mean:

- `rejected Unresolved Error text, lists steps (only a Success Process may): When a plate must be cleaned and placed in a microwave, search the diningtable a`
  - Code check: only a Success Process may list steps; other rule types must stay a condition -> action sentence.

## 4. What changed in the manual

Nothing visible changed (no rule added or edited).

