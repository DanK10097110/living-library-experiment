# A lost game: any rule written is a hidden, unconfirmed note

- Run `study`, stream `practice-E-0`, practice game #1. Condition E.
- Goal: **put a cloth in drawer.**   Kind: pick and place
- *What it shows:* Pick-and-place lost with 3 failed retries. The Builder writes a Special Phenomenon note ("ensure the container is open before placing"). Because no attempt won, it is stored with verified=false and never shown to the agent, and a Success Process attempt is refused ("a failure may not write a Success Process rule").

## 1. The practice game (first attempt)

Outcome: **LOST** in 30 steps (1 invalid).

Rules shown to the agent in this game (from the manual before the game):

- none (no rule of this kind existed yet)

Actions (`!` marks an invalid command):

```
go to drawer 1 | open drawer 1 | go to towelholder 1 | go to countertop 1 | go to towelholder 1 | go to countertop 1 | go to towelholder 2 | go to garbagecan 1 | go to countertop 1 | go to sinkbasin 1 | go to countertop 1 | go to towelholder 1 | go to countertop 1 | go to drawer 1 | go to countertop 1 | go to drawer 1 | go to towelholder 1 | go to countertop 1 | go to garbagecan 1 | !go to cabinet 1 | go to drawer 2 | open drawer 2 | go to countertop 1 | go to towelholder 1 | go to drawer 1 | go to drawer 3 | go to towelholder 1 | go to countertop 1 | go to drawer 4 | open drawer 4
```

## 2. Reflexion retries (ExpeL experience gathering)

A lost practice game is replayed from the start, up to 3 times, with the agent's own reflection on each failed attempt in its prompt; it stops at the first win. Retries change no memory.

**Attempt 1** (retry): lost in 30 steps.

Reflection on the previous failed attempt, given to the agent at the start of this attempt:

> "I repeatedly moved between the towelholder and drawers without ever picking up the towel or
> placing it in a drawer. Instead of just navigating to locations, I need to actually pick up the
> towel from towelholder 1 and then place it into one of the open drawers."

```
go to towelholder 1 | take towel 1 from towelholder 1 | go to drawer 1 | open drawer 1 | !move towel 1 to drawer 1 | !move towel 1 to drawer 2 | !move towel 1 to drawer 3 | go to towelholder 1 | go to drawer 1 | !move towel 1 to drawer 1 | !move towel 1 to drawer 2 | !open drawer 1 | !move towel 1 to drawer 4 | !go to drawer 1 | inventory | !go to drawer 1 | !move towel 1 to drawer 1 | !move towel 1 to drawer 1 | !move towel 1 to drawer 2 | go to drawer 3 | open drawer 3 | !move towel 1 to drawer 3 | !move towel 1 to drawer 3 | go to towelholder 1 | go to drawer 1 | !move towel 1 to drawer 1 | examine towel 1 | !move towel 1 to drawer 1 | inventory | !move towel 1 to drawer 1
```

**Attempt 2** (retry): lost in 30 steps.

Reflection on the previous failed attempt, given to the agent at the start of this attempt (the list of reflections grows; the model often repeats itself):

> "I failed because I repeatedly navigated to drawers and towelholders without successfully
> executing the 'move towel 1 to drawer X' action, likely due to not being in the correct position
> or the drawer not being properly open. Instead, I should ensure I am standing directly at the
> target drawer with it open before attempting to move the towel, and verify the action succeeds
> before moving to another"

```
go to towelholder 1 | take towel 1 from towelholder 1 | go to drawer 1 | open drawer 1 | !move towel 1 to drawer 1 | go to drawer 2 | open drawer 2 | !move towel 1 to drawer 2 | !move towel 1 to drawer 1 | go to drawer 1 | !move towel 1 to drawer 1 | !move towel 1 to drawer 1 | !move towel 1 to drawer 1 | go to towelholder 1 | inventory | go to drawer 1 | !move towel 1 to drawer 1 | go to drawer 2 | !move towel 1 to drawer 2 | !move towel 1 to drawer 2 | go to drawer 1 | !move towel 1 to drawer 1 | !move towel 1 to drawer 1 | go to drawer 2 | go to drawer 3 | open drawer 3 | !move towel 1 to drawer 3 | go to towelholder 1 | inventory | go to drawer 3
```

**Attempt 3** (retry): lost in 30 steps.

Reflection on the previous failed attempt, given to the agent at the start of this attempt (the list of reflections grows; the model often repeats itself):

> "I failed because I repeatedly navigated between locations without confirming the towel was
> actually in my inventory before attempting to move it, and I didn't verify the drawer was open
> before trying to place the item. Instead, I should first check my inventory to confirm I'm
> carrying the towel, ensure the target drawer is open, and then immediately execute the move action
> without unnecessary navi"

```
go to towelholder 1 | take towel 1 from towelholder 1 | go to drawer 1 | open drawer 1 | !move towel 1 to drawer 1 | !move towel 1 to drawer 1 | inventory | go to towelholder 1 | go to drawer 1 | !move towel 1 to drawer 1 | !move towel 1 to drawer 1 | !move towel 1 to drawer 1 | !move towel 1 to drawer 1 | inventory | go to drawer 2 | open drawer 2 | !move towel 1 to drawer 2 | !move towel 1 to drawer 2 | !move towel 1 to drawer 2 | !go to drawer 2 | !move towel 1 to drawer 2 | go to drawer 1 | !move towel 1 to drawer 1 | go to drawer 2 | go to drawer 1 | inventory | !move towel 1 to drawer 1 | !move towel 1 to drawer 1 | go to towelholder 1 | go to drawer 1
```

Retry cost: 102 model calls, 200,506 tokens; retry won: **False**.

## 3. Builder report

Case: **failure**  (first attempt lost); diagnosis: imperfect rules

- `outcome` the game was LOST; Beta(alpha, beta) of the shown rules [] updated (won: alpha+1, lost: beta+1); the won game's plan and steps are stored as evidence for the rules.
- `write_rule` **Special Phenomenon** (kind `pick_and_place_simple`, verified=False): "When placing an object in a container, ensure the container is open before attempting to place."  Example: _open drawer 1 before putting towel 1 in it._
- `pool_game` this never-won game (4 attempts: the first and each failed retry) is pooled by kind of task (`pick_and_place_simple`) for Anti-Pattern mining.

Log lines the Builder step produced (verbatim), with what they mean:

- `rule_1 is a hidden Builder note until a won game confirms it`
  - A rule written from a lost game is an unconfirmed guess: stored, but never shown to the agent yet.
- `a failure may not write a Success Process rule`
  - Guard: a lost game cannot write a recipe (Success Process).

## 4. What changed in the manual

- `rule_3` **NEW**
  - after:  [Special Phenomenon] Beta(1,1) visible=False: When placing an object in a container, ensure the container is open before attempting to place.

- Logging quirk worth knowing: the log line says "rule_1 is a hidden Builder note" but the new hidden rule has id rule_3 (the id printed was assigned before the failure pools took ids rule_2 and rule_4).