# E-minus (append-only) library after 40 practice games

26 entries: 5 recipes, 2 special phenomena, 5 corrected errors, 8 unresolved errors (hidden) and 6 pools.

Source: `study` / `practice-E-minus-0` after practice game #39.  **26 rules** (11 visible to the agent, 15 hidden Builder notes) plus 6 hidden failure pools (bookkeeping for Anti-Pattern mining).

Types: Success Process 5, Special Phenomenon 2, Failure Pool 6, Unresolved Error 8, Corrected Error 5

Beta(alpha, beta): reliability of the rule, starts Beta(1,1); every game where the rule was shown adds 1 to alpha if won, else to beta. mean = alpha/(alpha+beta).

| id | type | kind of task | Beta(a,b) | mean | visible | rule text |
|---|---|---|---|---|---|---|
| rule_24 | Corrected Error | look at object under a lamp | (1,1) | 0.5 | yes | When examining an object with a light source, verify the light source's location before attempting to take it. |
| rule_26 | Failure Pool | look at object under a lamp | (1,1) | 0.5 | HIDDEN | failure pool |
| rule_25 | Success Process | look at object under a lamp | (1,1) | 0.5 | yes | When examining an object with a light source: search all surfaces for the light source, navigate to where it is, use the light source, move the object to that location, take the object, and examine it with the light source. |
| rule_7 | Corrected Error | pick and place | (1,1) | 0.5 | yes | When attempting to go to a container, ensure you are currently positioned at that container before issuing the command. |
| rule_23 | Corrected Error | pick and place | (1,1) | 0.5 | yes | When moving an object to a target, ensure you are at the target before issuing the move command. |
| rule_5 | Failure Pool | pick and place | (1,1) | 0.5 | HIDDEN | failure pool |
| rule_8 | Success Process | pick and place | (1,1) | 0.5 | yes | When an object must be picked up and placed in a target: search all containers and surfaces first, open any closed containers, take the object, go to the target, open it if closed, and move the object there. |
| rule_4 | Unresolved Error | pick and place | (1,1) | 0.5 | HIDDEN | When placing an object in a container, verify the container is open and empty before attempting to move the object there. |
| rule_18 | Unresolved Error | pick and place | (1,1) | 0.5 | HIDDEN | When placing an object on a target, first search the entire environment for the object before attempting placement. |
| rule_22 | Corrected Error | clean then place | (1,1) | 0.5 | yes | When moving an object to a container, go to the container first before attempting to move the object there. |
| rule_3 | Failure Pool | clean then place | (1,1) | 0.5 | HIDDEN | failure pool |
| rule_2 | Special Phenomenon | clean then place | (1,1) | 0.5 | yes | When cleaning an object, use the sinkbasin as the cleaning appliance. |
| rule_1 | Success Process | clean then place | (1,1) | 0.5 | yes | When an object must be cleaned and placed in a container: search the object's current location first, take it, go to the sink, clean it with the sink, go to the container, and move it there. |
| rule_11 | Unresolved Error | clean then place | (1,1) | 0.5 | HIDDEN | When cleaning the object, search all surfaces before opening cabinets. |
| rule_17 | Corrected Error | cool then place | (1,1) | 0.5 | yes | When cooling an object with a fridge, ensure the fridge is open before cooling, and move the object to the target after cooling. |
| rule_14 | Failure Pool | cool then place | (1,1) | 0.5 | HIDDEN | failure pool |
| rule_16 | Success Process | cool then place | (1,1) | 0.5 | yes | When an object must be cooled and placed: search stoves first, take the object, go to the fridge, open it if closed, cool the object with the fridge, then move it to the target. |
| rule_13 | Unresolved Error | cool then place | (1,1) | 0.5 | HIDDEN | When a task requires taking a specific object from a container, systematically search all containers (including fridges) before attempting to take the object, as the object may not be present. |
| rule_19 | Unresolved Error | cool then place | (1,1) | 0.5 | HIDDEN | When a task requires cooling an object, systematically examine all countertops first to locate the object before using any appliance. |
| rule_20 | Unresolved Error | cool then place | (1,1) | 0.5 | HIDDEN | When cooling an object on a stoveburner, wait until it is safe to handle before moving it, and open the target container before attempting to place the object inside. |
| rule_10 | Failure Pool | heat then place | (1,1) | 0.5 | HIDDEN | failure pool |
| rule_9 | Special Phenomenon | heat then place | (1,1) | 0.5 | HIDDEN | When a task requires placing an object in a receptacle, search the receptacle first to confirm it is empty before attempting to place the object there. |
| rule_6 | Failure Pool | two objects | (1,1) | 0.5 | HIDDEN | failure pool |
| rule_12 | Success Process | two objects | (1,1) | 0.5 | yes | When two objects must be placed in a target: search for the objects first, take each one, go to the target, and move each object there. |
| rule_15 | Unresolved Error | two objects | (1,1) | 0.5 | HIDDEN | When searching for multiple objects, search all remaining locations before attempting to move any object. |
| rule_21 | Unresolved Error | two objects | (1,1) | 0.5 | HIDDEN | When moving multiple objects to a target, move each one directly to the target immediately after picking it up. |
