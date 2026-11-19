# Mature library: practice-d after 48 practice games (current code, no object names)

Current-code library with no object names. Contains some weak rules (e.g. rule_22 Beta(8,10) about `move`, a hidden note).

Source: `practice-d` / `practice-E-0` after practice game #47.  **28 rules** (16 visible to the agent, 12 hidden Builder notes) plus 6 hidden failure pools (bookkeeping for Anti-Pattern mining).

Types: Success Process 5, Special Phenomenon 4, Failure Pool 6, Unresolved Error 4, Corrected Error 9

Beta(alpha, beta): reliability of the rule, starts Beta(1,1); every game where the rule was shown adds 1 to alpha if won, else to beta. mean = alpha/(alpha+beta).

| id | type | kind of task | Beta(a,b) | mean | visible | rule text |
|---|---|---|---|---|---|---|
| rule_22 | Corrected Error | all | (8,10) | 0.44 | yes | When placing an object on a target, use 'move <object> to <target>' after taking it, not 'go to <target>' then 'take' again. |
| rule_23 | Corrected Error | look at object under a lamp | (1,2) | 0.33 | yes | When an object must be examined with a light source and the source is not visible on the target surface, examine the target and check other locations (drawers, dressers) for the light source. |
| rule_24 | Failure Pool | look at object under a lamp | (1,1) | 0.5 | HIDDEN | failure pool |
| rule_25 | Unresolved Error | look at object under a lamp | (1,1) | 0.5 | HIDDEN | When an object must be examined under a light source, verify the light source is on the target surface before placing the object there. |
| rule_12 | Corrected Error | pick and place | (5,3) | 0.62 | yes | When placing an object into a container, open the container if closed before attempting the move. |
| rule_5 | Failure Pool | pick and place | (1,1) | 0.5 | HIDDEN | failure pool |
| rule_16 | Special Phenomenon | pick and place | (1,1) | 0.5 | HIDDEN | When placing an object on a surface, verify the object is not already there before searching for it elsewhere. |
| rule_10 | Success Process | pick and place | (9,3) | 0.75 | yes | When an object must be picked up and placed: search surfaces first, then containers, take the object, go to the target, open the target if closed, move the object to the target. |
| rule_4 | Unresolved Error | pick and place | (1,1) | 0.5 | HIDDEN | When placing an object into a container, search all containers first to find one that accepts the object before attempting placement. |
| rule_8 | Unresolved Error | pick and place | (1,1) | 0.5 | HIDDEN | When an object must be picked up from a surface and placed in a container, examine the surface first to identify the object among visible items. |
| rule_3 | Failure Pool | clean then place | (1,1) | 0.5 | HIDDEN | failure pool |
| rule_2 | Special Phenomenon | clean then place | (5,4) | 0.56 | yes | When placing an object in a location, use the move command with the target location name. |
| rule_11 | Special Phenomenon | clean then place | (5,4) | 0.56 | yes | When a container is closed, open it before taking objects from it. |
| rule_1 | Success Process | clean then place | (5,4) | 0.56 | yes | When an object must be cleaned and placed: search the object's current location first, take it, clean it with the sinkbasin, then move it to the target location. |
| rule_15 | Corrected Error | cool then place | (2,4) | 0.33 | yes | When the object is already at the target, stop immediately instead of picking it up and moving it again. |
| rule_17 | Corrected Error | cool then place | (1,2) | 0.33 | yes | When cooling the object, first scan all countertops for the object before attempting to cool or store it. |
| rule_19 | Corrected Error | cool then place | (1,2) | 0.33 | yes | When cooling an object, place it on a safe surface first before attempting to move it to a container. |
| rule_20 | Corrected Error | cool then place | (2,4) | 0.33 | yes | When cooling an object, use the fridge instead of the sinkbasin. |
| rule_13 | Failure Pool | cool then place | (1,1) | 0.5 | HIDDEN | failure pool |
| rule_26 | Special Phenomenon | cool then place | (1,1) | 0.5 | HIDDEN | When placing an object in a microwave, open it first, verify the object is inside, then start the microwave before marking the task done. |
| rule_14 | Success Process | cool then place | (2,4) | 0.33 | yes | When an object must be cooled and placed: search stoveburners first, take the object, go to fridge, open if closed, cool the object with fridge, go to target, open if closed, move the object to target. |
| rule_18 | Corrected Error | heat then place | (4,1) | 0.8 | yes | When the object must be heated, use the microwave instead of the stoveburner. |
| rule_28 | Corrected Error | heat then place | (1,1) | 0.5 | yes | When placing an object on a table, go to the table first, then use 'move <object> to <table>' instead of trying to move directly from current location. |
| rule_9 | Failure Pool | heat then place | (1,1) | 0.5 | HIDDEN | failure pool |
| rule_27 | Success Process | heat then place | (1,1) | 0.5 | yes | When an object must be heated and placed in a container: search countertop first, take the object, open the microwave if closed, heat the object with the microwave, go to the target container, open it if closed, move the object to the container. |
| rule_7 | Failure Pool | two objects | (1,1) | 0.5 | HIDDEN | failure pool |
| rule_21 | Success Process | two objects | (2,3) | 0.4 | yes | When an object must be placed on a surface: search all surfaces first, open the target if closed, go to the target location, take the object from its source, go to the target location, move the object to the target. |
| rule_6 | Unresolved Error | two objects | (1,1) | 0.5 | HIDDEN | When placing multiple objects in a container, search all surfaces for all objects before opening any containers. |
