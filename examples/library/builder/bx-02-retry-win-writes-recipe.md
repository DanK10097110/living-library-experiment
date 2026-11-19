# ExpeL retry: loss -> reflection -> retry win -> recipe

- Run `practice-b`, stream `practice-E-0`, practice game #1. Condition E.
- Goal: **put a cloth in drawer.**   Kind: pick and place
- *What it shows:* First attempt on "put a cloth in drawer" lost (30 steps). The agent reflects ("I never found the cloth..."), replays the same game with that reflection and wins in 10 steps. The Builder contrasts both attempts and writes a Success Process.

## 1. The practice game (first attempt)

Outcome: **LOST** in 30 steps (1 invalid).

Rules shown to the agent in this game (from the manual before the game):

- none (no rule of this kind existed yet)

Actions (`!` marks an invalid command):

```
inventory | look | look | inventory | go to countertop 1 | look | go to drawer 1 | inventory | go to countertop 1 | go to drawer 1 | open drawer 1 | go to countertop 1 | examine countertop 1 | inventory | go to sinkbasin 1 | go to drawer 3 | inventory | inventory | examine drawer 3 | open drawer 3 | inventory | go to countertop 1 | go to drawer 1 | go to drawer 2 | open drawer 2 | go to drawer 4 | open drawer 4 | go to countertop 1 | examine countertop 1 | !<action> go to sinkbas
```

## 2. Reflexion retries (ExpeL experience gathering)

A lost practice game is replayed from the start, up to 3 times, with the agent's own reflection on each failed attempt in its prompt; it stops at the first win. Retries change no memory.

**Attempt 1** (retry): WON in 10 steps.

Reflection on the previous failed attempt, given to the agent at the start of this attempt:

> "I failed because I never found the cloth to put in the drawer; I only examined countertops and
> drawers without searching for the cloth object. Instead, I should have systematically searched all
> visible areas like countertops and drawers for the cloth before attempting to place it. I need to
> look more carefully at each location to find the cloth item."

```
go to countertop 1 | go to drawer 1 | go to countertop 1 | go to garbagecan 1 | go to sinkbasin 1 | go to toilet 1 | take cloth 1 from toilet 1 | go to drawer 1 | open drawer 1 | move cloth 1 to drawer 1
```

Retry cost: 12 model calls, 23,509 tokens; retry won: **True**.

## 3. Builder report

Case: **corrected failure**  (first attempt lost, retry won); diagnosis: imperfect rules

- `outcome` the game was LOST; Beta(alpha, beta) of the shown rules [] updated (won: alpha+1, lost: beta+1); the won game's plan and steps are stored as evidence for the rules.
- `write_rule` **Success Process** (kind `pick_and_place_simple`, verified=True): "When an object must be picked up and placed: search all visible areas first, take the object from its location, open the target container if closed, move the object there."  Example: _search toilet 1, sinkbasin 1, countertop 1, garbagecan 1, drawers; take cloth 1 from toilet 1; open drawer 1; move cloth 1 to drawer 1._
- `pool_won` this won attempt is stored in the hidden failure pool of its kind of task (used to check Anti-Pattern candidates against wins).

## 4. What changed in the manual

- `rule_3` **NEW**
  - after:  [Success Process] Beta(1,1) visible=True: When an object must be picked up and placed: search all visible areas first, take the object from its location, open the target container if closed, move the object there.
