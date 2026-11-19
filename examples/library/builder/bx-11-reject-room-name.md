# Rejected: a recipe that tells the agent to search "the room"

- Run `practice-e`, stream `practice-E-0`, practice game #38. Condition E.
- Goal: **examine the pen with the desklamp.**   Kind: look at object under a lamp
- *What it shows:* The Success Process text contains the word "room" ("search the current room for the object"); the rewrite was still specific and it is rejected.

## 1. The practice game (first attempt)

Outcome: **WON** in 4 steps (0 invalid).

Rules shown to the agent in this game (from the manual before the game):

- none (no rule of this kind existed yet)

Actions (`!` marks an invalid command):

```
go to desk 1 | take pen 2 from desk 1 | go to dresser 1 | use desklamp 1
```

## 2. Builder report

Case: **direct success**  (first attempt won); diagnosis: imperfect rules

- `outcome` the game was WON; Beta(alpha, beta) of the shown rules [] updated (won: alpha+1, lost: beta+1); the won game's plan and steps are stored as evidence for the rules.
- `pool_won` this won attempt is stored in the hidden failure pool of its kind of task (used to check Anti-Pattern candidates against wins).

Log lines the Builder step produced (verbatim), with what they mean:

- `rejected Success Process text, names specific objects or rooms (room): When an object must be examined with a light: search the current room for the ob`
  - Code check: a rule must not name a portable object kind or a room. The Builder got ONE rewrite ("use the object / the target"); the rewrite was still specific, so the rule was rejected.

## 3. What changed in the manual

Nothing visible changed (no rule added or edited).

