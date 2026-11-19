# Study E library after 35 practice games (current code, still growing)

16 rules: 9 visible (4 recipes, 2 special phenomena, 3 corrected errors), 1 Anti-Pattern, 1 hidden Unresolved Error and 5 failure pools.

Source: `study` / `practice-E-0` after practice game #34.  **16 rules** (9 visible to the agent, 7 hidden Builder notes) plus 5 hidden failure pools (bookkeeping for Anti-Pattern mining).

Types: Success Process 4, Failure Pool 5, Special Phenomenon 2, Unresolved Error 1, Corrected Error 3, Anti-Pattern 1

Beta(alpha, beta): reliability of the rule, starts Beta(1,1); every game where the rule was shown adds 1 to alpha if won, else to beta. mean = alpha/(alpha+beta).

| id | type | kind of task | Beta(a,b) | mean | visible | rule text |
|---|---|---|---|---|---|---|
| rule_4 | Failure Pool | pick and place | (1,1) | 0.5 | HIDDEN | failure pool |
| rule_3 | Special Phenomenon | pick and place | (4,3) | 0.57 | yes | When placing an object on a surface, no need to open the surface; when placing in a container, ensure the container is open before attempting to place. |
| rule_7 | Success Process | pick and place | (7,4) | 0.64 | yes | When an object must be picked up and placed: search drawers and containers first, take the object, go to the target, move the object there if the target is open or a surface. |
| rule_9 | Corrected Error | clean then place | (5,2) | 0.71 | yes | When opening a container, do not attempt to open a different container first; open the one you are currently at. |
| rule_2 | Failure Pool | clean then place | (1,1) | 0.5 | HIDDEN | failure pool |
| rule_1 | Success Process | clean then place | (5,2) | 0.71 | yes | When an object must be cleaned and placed: search the target location first, take the object, go to the sink, clean it with the sink, go to the target location, move it there. |
| rule_12 | Corrected Error | cool then place | (4,4) | 0.5 | yes | When an object must be cooled and placed, search countertops and cabinets first, then cool with the fridge, open the target if closed, and put it there. |
| rule_14 | Failure Pool | cool then place | (1,1) | 0.5 | HIDDEN | failure pool |
| rule_13 | Success Process | cool then place | (4,4) | 0.5 | yes | When an object must be cooled and placed in the target: search cabinets and countertops first, take the object, cool it with the fridge, open the target if closed, move the object there. |
| rule_16 | Anti-Pattern | heat then place | (1,1) | 0.5 | yes | When examining an appliance, do not issue the same "examine" command again and again. |
| rule_8 | Failure Pool | heat then place | (1,1) | 0.5 | HIDDEN | failure pool |
| rule_15 | Special Phenomenon | heat then place | (1,1) | 0.5 | HIDDEN | When heating an object on a stoveburner, examine it first to confirm it is hot before moving it to the target. |
| rule_11 | Corrected Error | two objects | (2,3) | 0.4 | yes | When move command fails, go to target container first before retrying move. |
| rule_6 | Failure Pool | two objects | (1,1) | 0.5 | HIDDEN | failure pool |
| rule_10 | Success Process | two objects | (2,3) | 0.4 | yes | When placing two objects in a bed: search furniture surfaces first, take each object, move to bed, if move fails go to bed then move again. |
| rule_5 | Unresolved Error | two objects | (1,1) | 0.5 | HIDDEN | When placing multiple objects in a container, search all possible furniture surfaces before opening any containers. |
