# The hidden note becomes visible: confirmed by a later retry win

- Run `study`, stream `practice-E-0`, practice game #9. Condition E.
- Goal: **put a cellphone in dresser.**   Kind: pick and place
- *What it shows:* rule_3 was written hidden at game 1. In game 9 the first attempt lost but a retry won; the Builder updated rule_3 ("Confirmed by successful retry where drawer 4 was opened before moving the object") and the log says "confirmed by a won game (now shown to the agent)". It also rewrites rule_7 to the new game's search order.

## 1. The practice game (first attempt)

Outcome: **LOST** in 30 steps (0 invalid).

Rules shown to the agent in this game (from the manual before the game):

- `rule_7` **Success Process** Beta(1,1): When an object must be picked up and placed: search drawers first, open the target container if closed, take the object, go to the target container, move the object there.

Actions (`!` marks an invalid command):

```
go to drawer 1 | go to dresser 1 | go to drawer 1 | open drawer 1 | go to drawer 2 | open drawer 2 | go to drawer 3 | open drawer 3 | open drawer 4 | go to drawer 5 | open drawer 5 | go to drawer 6 | open drawer 6 | go to drawer 7 | open drawer 7 | go to drawer 8 | open drawer 8 | go to drawer 1 | go to drawer 2 | go to drawer 3 | go to dresser 1 | go to drawer 4 | go to drawer 5 | go to drawer 6 | go to drawer 1 | go to drawer 9 | open drawer 9 | go to drawer 10 | go to drawer 8 | go to drawer 1
```

## 2. Reflexion retries (ExpeL experience gathering)

A lost practice game is replayed from the start, up to 3 times, with the agent's own reflection on each failed attempt in its prompt; it stops at the first win. Retries change no memory.

**Attempt 1** (retry): lost in 30 steps.

Reflection on the previous failed attempt, given to the agent at the start of this attempt:

> "I failed because I only opened drawers to check their contents but never located the cellphone
> itself. I should have first searched the dresser surface where the alarmclock, bowl, creditcard,
> and laptop were visible to find the cellphone before attempting to put it in any drawer."

```
go to dresser 1 | go to drawer 1 | open drawer 1 | go to drawer 2 | open drawer 2 | go to drawer 3 | open drawer 3 | open drawer 4 | go to drawer 5 | open drawer 5 | go to drawer 6 | open drawer 6 | go to dresser 1 | go to garbagecan 1 | go to laundryhamper 1 | go to drawer 1 | go to drawer 2 | go to drawer 7 | open drawer 7 | go to dresser 1 | examine dresser 1 | go to drawer 1 | go to drawer 3 | go to dresser 1 | go to drawer 4 | go to dresser 1 | go to drawer 5 | go to drawer 6 | go to drawer 8 | open drawer 8
```

**Attempt 2** (retry): lost in 30 steps.

Reflection on the previous failed attempt, given to the agent at the start of this attempt (the list of reflections grows; the model often repeats itself):

> "I failed because I only opened drawers to check their contents but never located the cellphone
> itself. I should have first searched the dresser surface where the alarmclock, bowl, creditcard,
> and laptop were visible to find the cellphone before attempting to put it in any drawer."

```
go to dresser 1 | go to drawer 1 | open drawer 1 | go to drawer 2 | open drawer 2 | go to drawer 3 | open drawer 3 | go to dresser 1 | go to drawer 4 | open drawer 4 | go to dresser 1 | look | go to laundryhamper 1 | go to dresser 1 | go to drawer 1 | go to laundryhamper 1 | !go to laundryhamper 1 | go to drawer 2 | go to dresser 1 | go to drawer 1 | go to drawer 3 | !go to drawer 4 | examine drawer 4 | go to dresser 1 | examine dresser 1 | go to drawer 1 | go to safe 1 | open safe 1 | go to dresser 1 | examine dresser 1
```

**Attempt 3** (retry): WON in 17 steps.

Reflection on the previous failed attempt, given to the agent at the start of this attempt (the list of reflections grows; the model often repeats itself):

> "I failed because I only opened drawers to check their contents but never located the cellphone
> itself. I should have first searched the dresser surface where the alarmclock, bowl, creditcard,
> and laptop were visible to find the cellphone before attempting to put it in any drawer."

```
go to dresser 1 | go to drawer 1 | open drawer 1 | go to drawer 2 | go to dresser 1 | go to drawer 1 | go to sidetable 1 | go to drawer 3 | go to dresser 1 | go to drawer 4 | open drawer 4 | go to dresser 1 | go to laundryhamper 1 | go to bed 1 | take cellphone 1 from bed 1 | go to dresser 1 | move cellphone 1 to dresser 1
```

Retry cost: 87 model calls, 195,026 tokens; retry won: **True**.

## 3. Builder report

Case: **corrected failure**  (first attempt lost, retry won); diagnosis: imperfect rules

- `outcome` the game was LOST; Beta(alpha, beta) of the shown rules ['rule_7'] updated (won: alpha+1, lost: beta+1); the won game's plan and steps are stored as evidence for the rules.
- `update_rule` rule_7: "When an object must be picked up and placed: search the target surface first, open the target container if closed, take the object from the surface, go to the target container, move the object there."  Validation note: _Agent failed by searching drawers first instead of the target surface where the object was located._
- `update_rule` rule_3: "When placing an object in a container, ensure the container is open before attempting to place."  Validation note: _Confirmed by successful retry where drawer 4 was opened before moving object to it._
- `pool_won` this won attempt is stored in the hidden failure pool of its kind of task (used to check Anti-Pattern candidates against wins).

Log lines the Builder step produced (verbatim), with what they mean:

- `rule_3 confirmed by a won game (now shown to the agent)`
  - A won game (or retry win) confirmed a hidden Builder note; it is now shown to the agent.

## 4. What changed in the manual

- `rule_3` **verified**
  - before: [Special Phenomenon] Beta(1,1) visible=False: When placing an object in a container, ensure the container is open before attempting to place.
  - after:  [Special Phenomenon] Beta(1,1) visible=True: When placing an object in a container, ensure the container is open before attempting to place.
- `rule_7` **rule, example, beta**
  - before: [Success Process] Beta(1,1) visible=True: When an object must be picked up and placed: search drawers first, open the target container if closed, take the object, go to the target container, move the object there.
  - after:  [Success Process] Beta(1,2) visible=True: When an object must be picked up and placed: search the target surface first, open the target container if closed, take the object from the surface, go to the target container, move the object there.
