# Mature library: practice-b after 48 practice games (stores plans, 1 Anti-Pattern)

22 rules with type, kind of task, Beta(alpha, beta) and text; includes an Anti-Pattern ("do not use the command done") and rule_10 with Beta(24,10) that was scoped "all" (the bug later fixed by the scope guard).

Source: `practice-b` / `practice-E-0` after practice game #47.  **22 rules** (14 visible to the agent, 8 hidden Builder notes) plus 6 hidden failure pools (bookkeeping for Anti-Pattern mining).

Types: Success Process 6, Failure Pool 6, Corrected Error 5, Special Phenomenon 2, Unresolved Error 2, Anti-Pattern 1

Beta(alpha, beta): reliability of the rule, starts Beta(1,1); every game where the rule was shown adds 1 to alpha if won, else to beta. mean = alpha/(alpha+beta).

| id | type | kind of task | Beta(a,b) | mean | visible | rule text |
|---|---|---|---|---|---|---|
| rule_10 | Corrected Error | all | (24,10) | 0.71 | yes | When an object must be cooled and placed, search kitchen areas first, cool with fridge if closed, then move to target. |
| rule_20 | Failure Pool | look at object under a lamp | (1,1) | 0.5 | HIDDEN | failure pool |
| rule_19 | Success Process | look at object under a lamp | (2,1) | 0.67 | yes | When an object must be examined with a light: search locations where the object was seen, take the object, search for the light source, turn it on, then examine the object. |
| rule_4 | Failure Pool | pick and place | (1,1) | 0.5 | HIDDEN | failure pool |
| rule_3 | Success Process | pick and place | (10,2) | 0.83 | yes | When an object must be picked up and placed: search all visible areas first, take the object from its location, open the target container if closed, go to the target location, then move the object to the target location. |
| rule_14 | Unresolved Error | pick and place | (1,1) | 0.5 | HIDDEN | When searching for an object to pick up, examine all visible surfaces first before checking closed containers. |
| rule_18 | Corrected Error | clean then place | (2,1) | 0.67 | yes | When an object must be cleaned and placed, do not waste time opening empty containers before checking countertops for the object. |
| rule_2 | Failure Pool | clean then place | (1,1) | 0.5 | HIDDEN | failure pool |
| rule_9 | Special Phenomenon | clean then place | (8,1) | 0.89 | yes | When a container is closed, open it before searching inside. |
| rule_12 | Special Phenomenon | clean then place | (7,1) | 0.88 | yes | When the target is a countertop, search cabinets first to find the object if not visible there. |
| rule_1 | Success Process | clean then place | (8,1) | 0.89 | yes | When an object must be cleaned and placed: search cabinets first, take the object, go to the sink, clean it with the sink, go to the target, move it there. |
| rule_22 | Anti-Pattern | cool then place | (1,1) | 0.5 | yes | When cooling an object, do not use the command "done". |
| rule_11 | Failure Pool | cool then place | (1,1) | 0.5 | HIDDEN | failure pool |
| rule_13 | Success Process | cool then place | (3,3) | 0.5 | yes | When an object must be cooled and placed: search stoveburners first, take the object, go to fridge, open it if closed, cool object with fridge, close fridge, go to target, move object to target. |
| rule_21 | Unresolved Error | cool then place | (1,1) | 0.5 | HIDDEN | When an object must be cooled and placed in a container, open the container and take the object out after placing it inside if the task requires removal. |
| rule_7 | Corrected Error | heat then place | (4,2) | 0.67 | yes | When a stoveburner already has a kettle on it, never place a mug on the stoveburner to heat it; use the microwave instead. |
| rule_15 | Corrected Error | heat then place | (4,1) | 0.8 | yes | When heating an object in a microwave, use the heat command instead of move to place it inside. |
| rule_8 | Failure Pool | heat then place | (1,1) | 0.5 | HIDDEN | failure pool |
| rule_16 | Success Process | heat then place | (4,1) | 0.8 | yes | When a hot cup must be placed on a countertop: search fridge first, take the cup, go to microwave, heat cup with microwave, go to countertop, move cup to countertop. |
| rule_5 | Corrected Error | two objects | (4,4) | 0.5 | yes | When two objects must be retrieved and placed, search visible surfaces first before opening closed containers. |
| rule_6 | Failure Pool | two objects | (1,1) | 0.5 | HIDDEN | failure pool |
| rule_17 | Success Process | two objects | (3,2) | 0.6 | yes | When two objects must be placed in a target location: search visible surfaces first, take each object, then move both to the target. |
