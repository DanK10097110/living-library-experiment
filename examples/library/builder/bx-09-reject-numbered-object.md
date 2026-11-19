# Rejected: a recipe that names a numbered object

- Run `practice-b`, stream `practice-E-0`, practice game #12. Condition E.
- Goal: **put a cool bowl in cabinet.**   Kind: cool then place
- *What it shows:* A cool task: the Builder's Success Process text mentions "fridge 1", so code rejects it and logs "names a numbered object". The rule is not added.

## 1. The practice game (first attempt)

Outcome: **LOST** in 30 steps (2 invalid).

Rules shown to the agent in this game (from the manual before the game):

- none (no rule of this kind existed yet)

Actions (`!` marks an invalid command):

```
go to countertop 1 | go to cabinet 1 | !go to cabinet 2 | go to cabinet 3 | open cabinet 3 | go to cabinet 4 | go to drawer 1 | go to cabinet 5 | go to countertop 2 | go to cabinet 6 | open cabinet 6 | go to cabinet 7 | open cabinet 7 | go to drawer 1 | go to countertop 1 | go to drawer 2 | go to cabinet 1 | !go to cabinet 2 | go to cabinet 3 | go to cabinet 4 | open cabinet 4 | go to cabinet 5 | go to cabinet 6 | go to cabinet 7 | go to cabinet 8 | open cabinet 8 | go to cabinet 9 | open cabinet 9 | go to drawer 1 | go to drawer 2
```

## 2. Reflexion retries (ExpeL experience gathering)

A lost practice game is replayed from the start, up to 3 times, with the agent's own reflection on each failed attempt in its prompt; it stops at the first win. Retries change no memory.

**Attempt 1** (retry): lost in 30 steps.

Reflection on the previous failed attempt, given to the agent at the start of this attempt:

> "I failed because I spent too much time checking empty cabinets and drawers without first locating
> the cool bowl on any countertop. I should have started by scanning countertop 1 and countertop 2
> for the bowl before attempting to open any cabinets. Once I find the bowl, I can then place it in
> an open cabinet like cabinet 3, 4, 6, 7, 8, or 9."

```
go to countertop 1 | go to countertop 2 | go to cabinet 1 | !go to cabinet 2 | go to countertop 1 | go to cabinet 1 | go to countertop 1 | go to drawer 1 | go to fridge 1 | go to countertop 1 | go to cabinet 1 | go to countertop 1 | go to countertop 2 | examine countertop 2 | go to cabinet 1 | !go to cabinet 2 | go to cabinet 3 | open cabinet 3 | go to countertop 2 | go to cabinet 1 | go to cabinet 4 | open cabinet 4 | go to cabinet 5 | go to countertop 1 | go to countertop 2 | examine countertop 2 | go to countertop 1 | go to countertop 2 | go to countertop 1 | go to countertop 2
```

**Attempt 2** (retry): WON in 8 steps.

Reflection on the previous failed attempt, given to the agent at the start of this attempt (the list of reflections grows; the model often repeats itself):

> "I failed because I repeatedly moved between locations and checked empty cabinets without first
> identifying where the cool bowl was located. I should have immediately scanned countertop 1 and
> countertop 2 to find the bowl before attempting to open any cabinets. Once I locate the bowl on a
> countertop, I can pick it up and place it directly into an open cabinet like cabinet 3 or cabinet
> 4."

```
go to countertop 1 | go to countertop 2 | go to diningtable 1 | take bowl 1 from diningtable 1 | go to fridge 1 | cool bowl 1 with fridge 1 | go to cabinet 1 | move bowl 1 to cabinet 1
```

Retry cost: 45 model calls, 130,077 tokens; retry won: **True**.

## 3. Builder report

Case: **corrected failure**  (first attempt lost, retry won); diagnosis: imperfect rules

- `outcome` the game was LOST; Beta(alpha, beta) of the shown rules [] updated (won: alpha+1, lost: beta+1); the won game's plan and steps are stored as evidence for the rules.
- `write_rule` **Corrected Error** (kind `all`, verified=True): "When the goal requires cooling an object, locate and take the object from a surface before attempting to open any cabinets."  Example: _The agent failed by checking empty cabinets first; it should have scanned diningtable 1 and countertop 1/2 to find the bowl before opening cabinets._
- `pool_won` this won attempt is stored in the hidden failure pool of its kind of task (used to check Anti-Pattern candidates against wins).

Log lines the Builder step produced (verbatim), with what they mean:

- `rejected Success Process text, names a numbered object ('fridge 1'): When an object must be cooled and placed in a cabinet: search diningtable and co`
  - Code check: a rule must not name a numbered object ("microwave 1"); one rewrite is not attempted for this, text is rejected.

## 4. What changed in the manual

- `rule_10` **NEW**
  - after:  [Corrected Error] Beta(1,1) visible=True: When the goal requires cooling an object, locate and take the object from a surface before attempting to open any cabinets.
