# Small library: study E after 10 practice games

A handful of recipes, a hidden note (confirmed in game 9) and failure pools.

Source: `study` / `practice-E-0` after practice game #9.  **11 rules** (6 visible to the agent, 5 hidden Builder notes) plus 4 hidden failure pools (bookkeeping for Anti-Pattern mining).

Types: Success Process 3, Failure Pool 4, Special Phenomenon 1, Unresolved Error 1, Corrected Error 2

Beta(alpha, beta): reliability of the rule, starts Beta(1,1); every game where the rule was shown adds 1 to alpha if won, else to beta. mean = alpha/(alpha+beta).

| id | type | kind of task | Beta(a,b) | mean | visible | rule text |
|---|---|---|---|---|---|---|
| rule_4 | Failure Pool | pick and place | (1,1) | 0.5 | HIDDEN | failure pool |
| rule_3 | Special Phenomenon | pick and place | (1,1) | 0.5 | yes | When placing an object in a container, ensure the container is open before attempting to place. |
| rule_7 | Success Process | pick and place | (1,2) | 0.33 | yes | When an object must be picked up and placed: search the target surface first, open the target container if closed, take the object from the surface, go to the target container, move the object there. |
| rule_9 | Corrected Error | clean then place | (1,1) | 0.5 | yes | When opening a container, do not attempt to open a different container first; open the one you are currently at. |
| rule_2 | Failure Pool | clean then place | (1,1) | 0.5 | HIDDEN | failure pool |
| rule_1 | Success Process | clean then place | (1,1) | 0.5 | yes | When an object must be cleaned and placed: search the table first, take the object, go to the sink, clean it with the sink, go to the target container, move it there. |
| rule_8 | Failure Pool | heat then place | (1,1) | 0.5 | HIDDEN | failure pool |
| rule_11 | Corrected Error | two objects | (1,1) | 0.5 | yes | When move command fails, go to target shelf first before retrying move. |
| rule_6 | Failure Pool | two objects | (1,1) | 0.5 | HIDDEN | failure pool |
| rule_10 | Success Process | two objects | (1,1) | 0.5 | yes | When placing two objects in a shelf: search desk first, take each object, move to shelf, if move fails go to shelf then move again. |
| rule_5 | Unresolved Error | two objects | (1,1) | 0.5 | HIDDEN | When placing multiple objects in a container, search all possible locations for the objects before opening any containers. |
