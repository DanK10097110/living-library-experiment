# Early library: study E after 4 practice games

After 4 games the study E manual has one recipe, one hidden note and one pool.

Source: `study` / `practice-E-0` after practice game #3.  **7 rules** (2 visible to the agent, 5 hidden Builder notes) plus 3 hidden failure pools (bookkeeping for Anti-Pattern mining).

Types: Success Process 2, Failure Pool 3, Special Phenomenon 1, Unresolved Error 1

Beta(alpha, beta): reliability of the rule, starts Beta(1,1); every game where the rule was shown adds 1 to alpha if won, else to beta. mean = alpha/(alpha+beta).

| id | type | kind of task | Beta(a,b) | mean | visible | rule text |
|---|---|---|---|---|---|---|
| rule_4 | Failure Pool | pick and place | (1,1) | 0.5 | HIDDEN | failure pool |
| rule_3 | Special Phenomenon | pick and place | (1,1) | 0.5 | HIDDEN | When placing an object in a container, ensure the container is open before attempting to place. |
| rule_7 | Success Process | pick and place | (1,1) | 0.5 | yes | When an object must be picked up and placed: search drawers first, open the target container if closed, take the object, go to the target container, move the object there. |
| rule_2 | Failure Pool | clean then place | (1,1) | 0.5 | HIDDEN | failure pool |
| rule_1 | Success Process | clean then place | (1,1) | 0.5 | yes | When an object must be cleaned and placed: search the table first, take the object, go to the sink, clean it with the sink, go to the target container, move it there. |
| rule_6 | Failure Pool | two objects | (1,1) | 0.5 | HIDDEN | failure pool |
| rule_5 | Unresolved Error | two objects | (1,1) | 0.5 | HIDDEN | When placing multiple objects in a container, search all possible locations for the objects before opening any containers. |
