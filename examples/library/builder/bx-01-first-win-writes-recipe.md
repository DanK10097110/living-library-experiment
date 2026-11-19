# Builder after the first win: write the Success Process (recipe)

- Run `study`, stream `practice-E-0`, practice game #0. Condition E.
- Goal: **clean some fork and put it in drawer.**   Kind: clean then place
- *What it shows:* First practice game, a won clean task. With no rule yet, the Builder writes a Success Process: a general condition -> steps sentence plus the winning game's own steps as the example. The Beta posterior starts at (1,1).

## 1. The practice game (first attempt)

Outcome: **WON** in 6 steps (0 invalid).

Rules shown to the agent in this game (from the manual before the game):

- none (no rule of this kind existed yet)

Actions (`!` marks an invalid command):

```
go to diningtable 1 | take fork 1 from diningtable 1 | go to sinkbasin 1 | clean fork 1 with sinkbasin 1 | go to drawer 1 | move fork 1 to drawer 1
```

## 2. Builder report

Case: **direct success**  (first attempt won); diagnosis: imperfect rules

- `outcome` the game was WON; Beta(alpha, beta) of the shown rules [] updated (won: alpha+1, lost: beta+1); the won game's plan and steps are stored as evidence for the rules.
- `write_rule` **Success Process** (kind `pick_clean_then_place_in_recep`, verified=True): "When an object must be cleaned and placed: search the table first, take the object, go to the sink, clean it with the sink, go to the target container, move it there."  Example: _go to diningtable 1, take fork 1, go to sinkbasin 1, clean fork 1 with sinkbasin 1, go to drawer 1, move fork 1 to drawer 1_
- `pool_won` this won attempt is stored in the hidden failure pool of its kind of task (used to check Anti-Pattern candidates against wins).

## 3. What changed in the manual

- `rule_1` **NEW**
  - after:  [Success Process] Beta(1,1) visible=True: When an object must be cleaned and placed: search the table first, take the object, go to the sink, clean it with the sink, go to the target container, move it there.
