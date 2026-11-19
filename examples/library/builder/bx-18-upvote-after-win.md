# Builder vote: upvote after a win

- Run `practice-b`, stream `practice-E-0`, practice game #18. Condition E.
- Goal: **clean some cloth and put it in countertop.**   Kind: clean then place
- *What it shows:* A clean task is won; the Builder upvotes two rules that were shown (rule_12 and rule_9) and updates rule_1. The Beta alpha of each rule shown is incremented by the outcome step regardless of the vote.

## 1. The practice game (first attempt)

Outcome: **WON** in 7 steps (0 invalid).

Rules shown to the agent in this game (from the manual before the game):

- `rule_1` **Success Process** Beta(2,1): When an object must be cleaned and placed: search cabinets first, take the object, go to the sink, clean it with the sink, go to the target, move it there.
- `rule_9` **Special Phenomenon** Beta(2,1): When a container is closed, open it before searching inside.
- `rule_12` **Special Phenomenon** Beta(1,1): When the target is a countertop, search cabinets first to find the object if not visible there.
- `rule_10` **Corrected Error** Beta(1,3): When the goal requires cooling an object, locate and take the object from a surface before attempting to open any cabinets.

Actions (`!` marks an invalid command):

```
go to cabinet 1 | open cabinet 1 | take cloth 3 from cabinet 1 | go to sinkbasin 1 | clean cloth 3 with sinkbasin 1 | go to countertop 1 | move cloth 3 to countertop 1
```

## 2. Builder report

Case: **direct success**  (first attempt won); diagnosis: imperfect rules

- `outcome` the game was WON; Beta(alpha, beta) of the shown rules ['rule_1', 'rule_9', 'rule_12', 'rule_10'] updated (won: alpha+1, lost: beta+1); the won game's plan and steps are stored as evidence for the rules.
- `update_rule` rule_1: "When an object must be cleaned and placed: search cabinets first, take the object, go to the sink, clean it with the sink, go to the target, move it there."  Validation note: _This game confirms searching cabinets first and moving the object to the target after cleaning. | This game confirms searching cabinets first and moving the object to the target after cleaning._
- `upvote_rule` rule_12 (Builder vote on a rule that was shown)
- `upvote_rule` rule_9 (Builder vote on a rule that was shown)
- `pool_won` this won attempt is stored in the hidden failure pool of its kind of task (used to check Anti-Pattern candidates against wins).

## 3. What changed in the manual

- `rule_1` **example, alpha**
  - before: [Success Process] Beta(2,1) visible=True: When an object must be cleaned and placed: search cabinets first, take the object, go to the sink, clean it with the sink, go to the target, move it there.
  - after:  [Success Process] Beta(3,1) visible=True: When an object must be cleaned and placed: search cabinets first, take the object, go to the sink, clean it with the sink, go to the target, move it there.
- `rule_9` **alpha**
  - before: [Special Phenomenon] Beta(2,1) visible=True: When a container is closed, open it before searching inside.
  - after:  [Special Phenomenon] Beta(3,1) visible=True: When a container is closed, open it before searching inside.
- `rule_10` **alpha**
  - before: [Corrected Error] Beta(1,3) visible=True: When the goal requires cooling an object, locate and take the object from a surface before attempting to open any cabinets.
  - after:  [Corrected Error] Beta(2,3) visible=True: When the goal requires cooling an object, locate and take the object from a surface before attempting to open any cabinets.
- `rule_12` **alpha**
  - before: [Special Phenomenon] Beta(1,1) visible=True: When the target is a countertop, search cabinets first to find the object if not visible there.
  - after:  [Special Phenomenon] Beta(2,1) visible=True: When the target is a countertop, search cabinets first to find the object if not visible there.
