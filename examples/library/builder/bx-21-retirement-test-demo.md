# Retirement test (Beta posterior vs the base win rate of the kind of task)

**Honest note:** no rule was retired in any recorded practice run (the checkpoint logs contain no `retired ...` line), so there is no recorded retirement event to replay. The only recorded removals are from older code (capacity pruning: "removed rule_15 (importance reached 0)", see `results/study-E-library-at-gate.txt`). What follows is the CURRENT retirement code (`manual.retirable`) applied to REAL saved rules, and a what-if in which the weakest real rules lose more games.

## Rule of the code

- A rule shown in at least 4 practice games is retired (logged) when it never won, or when its Beta(1+won, 1+lost) posterior puts its win rate below the Laplace-smoothed base win rate of its kind of task with probability >= 0.9.
- An Anti-Pattern is retired only when the agent did the avoided thing in every game it was shown in.

## Real rules and the test today

| run | rule | type | won/lost while shown | base (won/games of the kind) | retire now? | text |
|---|---|---|---|---|---|---|
| study | rule_1 | Success Process | 4/1 | 5/7 | keep | When an object must be cleaned and placed: search the target location first, take the object, go to the sink,  |
| study | rule_3 | Special Phenomenon | 3/2 | 8/11 | keep | When placing an object on a surface, no need to open the surface; when placing in a container, ensure the cont |
| study | rule_7 | Success Process | 6/3 | 7/10 | keep | When an object must be picked up and placed: search drawers and containers first, take the object, go to the t |
| study | rule_9 | Corrected Error | 4/1 | 4/5 | keep | When opening a container, do not attempt to open a different container first; open the one you are currently a |
| study | rule_10 | Success Process | 1/2 | 1/4 | keep | When placing two objects in a bed: search furniture surfaces first, take each object, move to bed, if move fai |
| study | rule_11 | Corrected Error | 1/2 | 1/4 | keep | When move command fails, go to target container first before retrying move. |
| study | rule_12 | Corrected Error | 3/3 | 3/6 | keep | When an object must be cooled and placed, search countertops and cabinets first, then cool with the fridge, op |
| study | rule_13 | Success Process | 3/3 | 3/6 | keep | When an object must be cooled and placed in the target: search cabinets and countertops first, take the object |
| practice-b | rule_1 | Success Process | 7/0 | 8/9 | keep | When an object must be cleaned and placed: search cabinets first, take the object, go to the sink, clean it wi |
| practice-b | rule_3 | Success Process | 9/1 | 11/12 | keep | When an object must be picked up and placed: search all visible areas first, take the object from its location |
| practice-b | rule_5 | Corrected Error | 3/3 | 3/8 | keep | When two objects must be retrieved and placed, search visible surfaces first before opening closed containers. |
| practice-b | rule_7 | Corrected Error | 3/1 | 3/4 | keep | When a stoveburner already has a kettle on it, never place a mug on the stoveburner to heat it; use the microw |
| practice-b | rule_9 | Special Phenomenon | 7/0 | 7/7 | keep | When a container is closed, open it before searching inside. |
| practice-b | rule_10 | Corrected Error | 23/9 | 25/35 | keep | When an object must be cooled and placed, search kitchen areas first, cool with fridge if closed, then move to |
| practice-b | rule_12 | Special Phenomenon | 6/0 | 6/6 | keep | When the target is a countertop, search cabinets first to find the object if not visible there. |
| practice-b | rule_13 | Success Process | 2/2 | 4/7 | keep | When an object must be cooled and placed: search stoveburners first, take the object, go to fridge, open it if |
| practice-b | rule_15 | Corrected Error | 3/0 | 3/3 | keep | When heating an object in a microwave, use the heat command instead of move to place it inside. |
| practice-b | rule_16 | Success Process | 3/0 | 3/3 | keep | When a hot cup must be placed on a countertop: search fridge first, take the cup, go to microwave, heat cup wi |
| practice-b | rule_17 | Success Process | 2/1 | 3/5 | keep | When two objects must be placed in a target location: search visible surfaces first, take each object, then mo |
| practice-d | rule_1 | Success Process | 4/3 | 5/9 | keep | When an object must be cleaned and placed: search the object's current location first, take it, clean it with  |
| practice-d | rule_2 | Special Phenomenon | 4/3 | 5/9 | keep | When placing an object in a location, use the move command with the target location name. |
| practice-d | rule_10 | Success Process | 8/2 | 8/10 | keep | When an object must be picked up and placed: search surfaces first, then containers, take the object, go to th |
| practice-d | rule_11 | Special Phenomenon | 4/3 | 4/7 | keep | When a container is closed, open it before taking objects from it. |
| practice-d | rule_12 | Corrected Error | 4/2 | 7/9 | keep | When placing an object into a container, open the container if closed before attempting the move. |
| practice-d | rule_14 | Success Process | 1/3 | 2/7 | keep | When an object must be cooled and placed: search stoveburners first, take the object, go to fridge, open if cl |
| practice-d | rule_15 | Corrected Error | 1/3 | 2/7 | keep | When the object is already at the target, stop immediately instead of picking it up and moving it again. |
| practice-d | rule_18 | Corrected Error | 3/0 | 3/3 | keep | When the object must be heated, use the microwave instead of the stoveburner. |
| practice-d | rule_20 | Corrected Error | 1/3 | 1/4 | keep | When cooling an object, use the fridge instead of the sinkbasin. |
| practice-d | rule_21 | Success Process | 1/2 | 2/5 | keep | When an object must be placed on a surface: search all surfaces first, open the target if closed, go to the ta |
| practice-d | rule_22 | Corrected Error | 7/9 | 7/16 | keep | When placing an object on a target, use 'move <object> to <target>' after taking it, not 'go to <target>' then |
| practice-e | rule_1 | Success Process | 5/2 | 5/9 | keep | When an object must be cleaned and placed: search the object's current location first, clean it with the sinkb |
| practice-e | rule_2 | Special Phenomenon | 5/2 | 5/9 | keep | When placing an object in a container, the container must be opened before moving the object inside. |
| practice-e | rule_4 | Success Process | 7/3 | 9/12 | keep | When an object must be placed on a target: search the area first, open any closed containers, take the object, |
| practice-e | rule_6 | Special Phenomenon | 2/1 | 3/8 | keep | When searching for the object, search furniture surfaces first before opening any drawers or cabinets. |
| practice-e | rule_11 | Corrected Error | 3/3 | 3/7 | keep | When two objects must be placed in a target: search furniture surfaces first, take each object, move it to the |
| practice-e | rule_15 | Success Process | 2/2 | 2/7 | keep | When an object must be cooled and placed: search for the object first, take it, cool it with the fridge, then  |
| practice-e | rule_16 | Corrected Error | 2/1 | 2/3 | keep | When the object must be heated and placed in a receptacle, go to the target receptacle after heating instead o |
| practice-e | rule_17 | Success Process | 2/1 | 2/4 | keep | When placing multiple objects in a target, search all furniture surfaces first, then navigate to the target be |
| mini-macla | rule_1 | Success Process | 5/2 | 5/9 | keep | When an object must be cleaned and placed: search the object's current location first, clean it with the sinkb |
| mini-macla | rule_3 | Success Process | 8/2 | 10/12 | keep | When an object must be picked up and placed: search all rooms first, open the target if closed, take the objec |
| mini-macla | rule_4 | Special Phenomenon | 8/2 | 10/12 | keep | When a container is closed, open it before moving objects into it. |
| mini-macla | rule_11 | Corrected Error | 5/2 | 5/7 | keep | When a task requires a clean object, clean it at sinkbasin before placing it in the target. |
| mini-macla | rule_12 | Corrected Error | 3/3 | 3/7 | keep | When two objects must be placed in a target, search drawers first, take each object, then move to the target a |
| mini-macla | rule_13 | Corrected Error | 5/1 | 8/9 | keep | When an object must be picked up and placed: use inventory to check if carrying the object before searching lo |
| mini-macla | rule_14 | Corrected Error | 3/1 | 3/8 | keep | When searching for a cool plate to place in a cabinet, systematically check all countertops first before attem |
| mini-macla | rule_16 | Success Process | 3/1 | 3/7 | keep | When an object must be cooled and placed: search all countertops first, open them if closed, take the object,  |
| mini-macla | rule_17 | Corrected Error | 2/1 | 2/3 | keep | When a task requires heating an object before placing it, use the correct heating appliance (e.g., microwave)  |
| mini-macla | rule_18 | Success Process | 2/1 | 2/3 | keep | When an object must be heated and placed: search countertops first, take the object, open the microwave if clo |
| mini-macla | rule_19 | Corrected Error | 3/1 | 3/4 | keep | When searching for a tomato to cool, check countertops and fridge contents first before exhaustively opening c |

## What-if: the weakest real rules after more lost games

Each row is the retirement test on the saved rule after N more games in which it is shown and lost (the base rate also gets N more lost games of that kind, which is the conservative case).

### practice-d rule_14: When an object must be cooled and placed: search stoveburners first, take the object, go to fridge, open if closed, cool

| extra lost games | won/lost | base | retired? |
|---|---|---|---|
| 0 | 1/3 | 2/7 | no |
| 1 | 1/4 | 2/8 | no |
| 2 | 1/5 | 2/9 | no |
| 3 | 1/6 | 2/10 | no |
| 4 | 1/7 | 2/11 | no |
| 5 | 1/8 | 2/12 | no |
| 6 | 1/9 | 2/13 | no |

### practice-d rule_20: When cooling an object, use the fridge instead of the sinkbasin.

| extra lost games | won/lost | base | retired? |
|---|---|---|---|
| 0 | 1/3 | 1/4 | no |
| 1 | 1/4 | 1/5 | no |
| 2 | 1/5 | 1/6 | no |
| 3 | 1/6 | 1/7 | no |
| 4 | 1/7 | 1/8 | no |
| 5 | 1/8 | 1/9 | no |
| 6 | 1/9 | 1/10 | no |

### practice-d rule_15: When the object is already at the target, stop immediately instead of picking it up and moving it again.

| extra lost games | won/lost | base | retired? |
|---|---|---|---|
| 0 | 1/3 | 2/7 | no |
| 1 | 1/4 | 2/8 | no |
| 2 | 1/5 | 2/9 | no |
| 3 | 1/6 | 2/10 | no |
| 4 | 1/7 | 2/11 | no |
| 5 | 1/8 | 2/12 | no |
| 6 | 1/9 | 2/13 | no |

### practice-d rule_22: When placing an object on a target, use 'move <object> to <target>' after taking it, not 'go to <target>' then 'take' ag

| extra lost games | won/lost | base | retired? |
|---|---|---|---|
| 0 | 7/9 | 7/16 | no |
| 1 | 7/10 | 7/17 | no |
| 2 | 7/11 | 7/18 | no |
| 3 | 7/12 | 7/19 | no |
| 4 | 7/13 | 7/20 | no |
| 5 | 7/14 | 7/21 | no |
| 6 | 7/15 | 7/22 | no |
