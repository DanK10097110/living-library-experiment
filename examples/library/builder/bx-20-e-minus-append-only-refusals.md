# E-minus: append-only, refused edits

- Run `study`, stream `practice-E-minus-0`, practice game #11. Condition E-minus (append-only).
- Goal: **put a keychain in desk.**   Kind: pick and place
- *What it shows:* E-minus runs the same practice games and retries as E but its manual is append-only: updates, votes, merges and refinement are refused ("append-only manual: rules cannot be changed"). The same game for E (appended below) updated rule_7 and rule_3.

## 1. The practice game (first attempt)

Outcome: **WON** in 30 steps (2 invalid).

Rules shown to the agent in this game (from the manual before the game):

- `rule_8` **Success Process** Beta(1,1): When an object must be picked up and placed in a target: search all containers and surfaces first, open any closed containers, take the object, go to the target, open it if closed, and move the object there.
- `rule_7` **Corrected Error** Beta(1,1): When attempting to go to a container, ensure you are currently positioned at that container before issuing the command.

Actions (`!` marks an invalid command):

```
go to desk 1 | go to cabinet 1 | open cabinet 1 | open cabinet 2 | go to drawer 1 | open drawer 1 | go to drawer 2 | open drawer 2 | go to cabinet 3 | open cabinet 3 | !go to shelf 1 | go to desk 1 | go to cabinet 4 | open cabinet 4 | go to drawer 1 | go to desk 1 | go to drawer 1 | go to desk 1 | go to garbagecan 1 | go to cabinet 1 | !go to cabinet 2 | go to cabinet 3 | go to cabinet 2 | go to cabinet 4 | go to drawer 1 | go to bed 1 | go to sidetable 1 | take keychain 1 from sidetable 1 | go to desk 1 | move keychain 1 to desk 1
```

## 2. Builder report

Case: **indirect success**  (first attempt won); diagnosis: imperfect rules

- `pool_won` this won attempt is stored in the hidden failure pool of its kind of task (used to check Anti-Pattern candidates against wins).

Log lines the Builder step produced (verbatim), with what they mean:

- `append-only manual: rules cannot be changed`
  - E-minus: the Builder asked to change an existing rule and was refused (append-only ablation).
- `append-only manual: rules cannot be changed`
  - E-minus: the Builder asked to change an existing rule and was refused (append-only ablation).

## 3. What changed in the manual

Nothing visible changed (no rule added or edited).


## The same practice game in E (for contrast)

E-minus game 11: **put a keychain in desk.** (won). E game 11: **put a keychain in desk.** (won). Same task.

E Builder report for its game 11 (updates are allowed):

- `update_rule` rule_7 -> "When an object must be picked up and placed: search drawers first, open the target container if closed, take the object, go to the target container, move the object there."
- `update_rule` rule_3 -> "When placing an object in a container, ensure the container is open before attempting to place."
- log: `rule_3 confirmed by a won game (now shown to the agent)`

E-minus game 11 log lines (every change refused):

- log: `append-only manual: rules cannot be changed`
- log: `append-only manual: rules cannot be changed`
