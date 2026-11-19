# Best library so far: the frozen avoid-rules practice library that won 54/70 dev games

26 entries including hidden notes and failure pools. Used in the paired-heat, cool and two-object examples of this folder.

Source: `check-avoid70` / `practice-E-0` after practice game #0.  **26 rules** (15 visible to the agent, 11 hidden Builder notes) plus 6 hidden failure pools (bookkeeping for Anti-Pattern mining).

Types: Success Process 6, Failure Pool 6, Special Phenomenon 2, Corrected Error 8, Unresolved Error 4

Beta(alpha, beta): reliability of the rule, starts Beta(1,1); every game where the rule was shown adds 1 to alpha if won, else to beta. mean = alpha/(alpha+beta).

| id | type | kind of task | Beta(a,b) | mean | visible | rule text |
|---|---|---|---|---|---|---|
| rule_22 | Corrected Error | look at object under a lamp | (1,2) | 0.33 | yes | When examining an object with a desklamp, turn on the desklamp before examining the object. |
| rule_24 | Failure Pool | look at object under a lamp | (1,1) | 0.5 | HIDDEN | failure pool |
| rule_23 | Success Process | look at object under a lamp | (1,2) | 0.33 | yes | When examining an object with a desklamp: find the object, take it, go to the desklamp's location, use the desklamp, then examine the object. |
| rule_13 | Corrected Error | pick and place | (6,2) | 0.75 | yes | When an object must be picked up and placed: use inventory to check if carrying the object before searching locations. |
| rule_5 | Failure Pool | pick and place | (1,1) | 0.5 | HIDDEN | failure pool |
| rule_4 | Special Phenomenon | pick and place | (9,3) | 0.75 | yes | When a container is closed, open it before moving objects into it. |
| rule_3 | Success Process | pick and place | (9,3) | 0.75 | yes | When an object must be picked up and placed: search all rooms first, open the target if closed, take the object from its location, move the object to the target. |
| rule_11 | Corrected Error | clean then place | (6,3) | 0.67 | yes | When a task requires a clean object, clean it at sinkbasin before placing it in the target. |
| rule_2 | Failure Pool | clean then place | (1,1) | 0.5 | HIDDEN | failure pool |
| rule_1 | Success Process | clean then place | (6,3) | 0.67 | yes | When an object must be cleaned and placed: search the object's current location first, clean it with the sinkbasin, then move it to the target. |
| rule_10 | Unresolved Error | clean then place | (1,1) | 0.5 | HIDDEN | When a plate must be cleaned and placed in microwave, search diningtable first before checking cabinets or fridge. |
| rule_20 | Unresolved Error | clean then place | (1,1) | 0.5 | HIDDEN | When a fork must be cleaned and placed, search all cabinets and drawers systematically before attempting to clean it. |
| rule_26 | Unresolved Error | clean then place | (1,1) | 0.5 | HIDDEN | When placing an object in a container, ensure the container is open and the object is not already on a surface before attempting placement. |
| rule_14 | Corrected Error | cool then place | (4,2) | 0.67 | yes | When searching for a cool plate to place in a cabinet, systematically check all countertops first before attempting to retrieve it from the fridge. |
| rule_19 | Corrected Error | cool then place | (4,2) | 0.67 | yes | When searching for a tomato to cool, check countertops and fridge contents first before exhaustively opening cabinets and drawers. |
| rule_15 | Failure Pool | cool then place | (1,1) | 0.5 | HIDDEN | failure pool |
| rule_25 | Special Phenomenon | cool then place | (1,1) | 0.5 | HIDDEN | When placing a cooled object in a microwave, explicitly start the heating cycle after closing the door. |
| rule_16 | Success Process | cool then place | (4,2) | 0.67 | yes | When an object must be cooled and placed: search all countertops first, open them if closed, take the object, cool it with the fridge, move it to the target. |
| rule_17 | Corrected Error | heat then place | (3,2) | 0.6 | yes | When a task requires heating an object before placing it, use the correct heating appliance (e.g., microwave) instead of attempting to cook on a stoveburner that shows nothing. |
| rule_9 | Failure Pool | heat then place | (1,1) | 0.5 | HIDDEN | failure pool |
| rule_18 | Success Process | heat then place | (3,2) | 0.6 | yes | When an object must be heated and placed: search countertops first, take the object, open the microwave if closed, heat the object with the microwave, move it to the target. |
| rule_8 | Unresolved Error | heat then place | (1,1) | 0.5 | HIDDEN | When heating water for a hot mug, do not repeatedly move the kettle between locations or examine the stoveburner without actually heating the water. |
| rule_6 | Corrected Error | two objects | (1,1) | 0.5 | yes | When multiple objects must be collected and placed, examine surfaces for them before opening storage, and re-examine surfaces after taking objects. |
| rule_12 | Corrected Error | two objects | (4,4) | 0.5 | yes | When two objects must be placed in a target, search drawers first, take each object, then move to the target and place it there. |
| rule_7 | Failure Pool | two objects | (1,1) | 0.5 | HIDDEN | failure pool |
| rule_21 | Success Process | two objects | (1,2) | 0.33 | yes | When two objects must be collected and placed: search surfaces first, take each object, go to target, move object to target. |
