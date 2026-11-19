# E: a win that is slower than C (28 steps vs 10)

- Condition: **E**   Kind of task: clean then place (`pick_clean_then_place_in_recep`)
- Goal: **clean some tomato and put it in countertop.**
- Game: `valid_seen/pick_clean_then_place_in_recep-Tomato-None-CounterTop-25/trial_T20190909_012550_586494`
- Source: run=check-e, stream=development-E-11, position=67, library=check-e practice library, frozen (22 entries)
- Outcome: **WON** in 28 steps (8 invalid), 30 model calls, 79,117 tokens

## Rules shown to planner and actor

- `rule_1` **Success Process**, kind `pick_clean_then_place_in_recep`, Beta(6,3) mean 0.67
  > When an object must be cleaned and placed: search the object's current location first, clean it with the sinkbasin, then move it to the target location.
  > Example: go to bathtubbasin 1, take cloth 1 from bathtubbasin 1, go to sinkbasin 1, clean cloth 1 with sinkbasin 1, go to toilet 1, move cloth 1 to toilet 1
- `rule_2` **Special Phenomenon**, kind `pick_clean_then_place_in_recep`, Beta(6,3) mean 0.67
  > When placing an object in a container, the container must be opened before moving the object inside.
  > Example: go to cabinet 1, open cabinet 1, move winebottle 2 to cabinet 1
- `rule_9` **Corrected Error**, kind `pick_clean_then_place_in_recep`, Beta(1,1) mean 0.5
  > When the target object must be found, never open cabinets or drawers first; scan the bathtubbasin and countertops first.
  > Example: Agent wasted time opening multiple cabinets without finding the cloth, which was in the bathtubbasin.

## Planner subgoals

1. find the tomato by examining locations
2. take the tomato from its current location
3. go to sinkbasin 1 to clean the tomato
4. clean the tomato with sinkbasin 1
5. go to countertop 1 to place the tomato
6. put the clean tomato on countertop 1

## Transcript

Initial observation:

```
-= Welcome to TextWorld, ALFRED! =-

You are in the middle of a room. Looking quickly around you, you see a cabinet 13, a cabinet 12, a cabinet 11, a cabinet 10, a cabinet 9, a cabinet 8, a cabinet 7, a cabinet 6, a cabinet 5, a cabinet 4, a cabinet 3, a cabinet 2, a cabinet 1, a coffeemachine 1, a countertop 1, a drawer 5, a drawer 4, a drawer 3, a drawer 2, a drawer 1, a fridge 1, a garbagecan 1, a microwave 1, a sinkbasin 1, a stoveburner 4, a stoveburner 3, a stoveburner 2, a stoveburner 1, and a toaster 1.

Your task is to: clean some tomato and put it in countertop.
```

**1.** `> go to fridge 1`  
   You arrive at fridge 1. The fridge 1 is closed.

**2.** `> go to countertop 1`  
   You arrive at countertop 1. On the countertop 1, you see a bread 1, a butterknife 1, a dishsponge 1, a fork 1, a knife 1, a mug 3, a pan 1, a peppershaker 2, a saltshaker 2, a saltshaker 1, a soapbottle 1, and a spoon 2.

**3.** `> go to garbagecan 1`  
   You arrive at garbagecan 1. On the garbagecan 1, you see a soapbottle 3.

**4.** `> go to cabinet 1`  
   You arrive at cabinet 1. The cabinet 1 is closed.

**5.** `> open cabinet 1`  
   You open the cabinet 1. The cabinet 1 is open. In it, you see nothing.

**6.** `> go to fridge 1`  
   You arrive at fridge 1. The fridge 1 is closed.

**7.** `> go to diningtable 1`  **[invalid action]**  
   You arrive at fridge 1. The fridge 1 is closed.

**8.** `> go to diningtable 1`  **[invalid action]**  
   You arrive at fridge 1. The fridge 1 is closed.

**9.** `> go to diningtable 1`  **[invalid action]**  
   You arrive at fridge 1. The fridge 1 is closed.

**10.** `> go to diningtable 1`  **[invalid action]**  
   You arrive at fridge 1. The fridge 1 is closed.

**11.** `> go to diningtable 1`  **[invalid action]**  
   You arrive at fridge 1. The fridge 1 is closed.

**12.** `> go to diningtable 1`  **[invalid action]**  
   You arrive at fridge 1. The fridge 1 is closed.

**13.** `> examine fridge 1`  
   The fridge 1 is closed.

**14.** `> go to diningtable 1`  **[invalid action]**  
   The fridge 1 is closed.

**15.** `> go to garbagecan 1`  
   You arrive at garbagecan 1. On the garbagecan 1, you see a soapbottle 3.

**16.** `> go to countertop 1`  
   You arrive at countertop 1. On the countertop 1, you see a bread 1, a butterknife 1, a dishsponge 1, a fork 1, a knife 1, a mug 3, a pan 1, a peppershaker 2, a saltshaker 2, a saltshaker 1, a soapbottle 1, and a spoon 2.

**17.** `> go to diningtable 1`  **[invalid action]**  
   You arrive at countertop 1. On the countertop 1, you see a bread 1, a butterknife 1, a dishsponge 1, a fork 1, a knife 1, a mug 3, a pan 1, a peppershaker 2, a saltshaker 2, a saltshaker 1, a soapbottle 1, and a spoon 2.

**18.** `> go to cabinet 1`  
   You arrive at cabinet 1. The cabinet 1 is open. In it, you see nothing.

**19.** `> go to stoveburner 1`  
   You arrive at stoveburner 1. On the stoveburner 1, you see a pot 1.

**20.** `> go to cabinet 2`  
   You arrive at cabinet 2. The cabinet 2 is closed.

**21.** `> open cabinet 2`  
   You open the cabinet 2. The cabinet 2 is open. In it, you see a peppershaker 1.

**22.** `> go to fridge 1`  
   You arrive at fridge 1. The fridge 1 is closed.

**23.** `> open fridge 1`  
   You open the fridge 1. The fridge 1 is open. In it, you see a bowl 1, a egg 1, a lettuce 2, a lettuce 1, a mug 2, a mug 1, a potato 1, and a tomato 1.

**24.** `> take tomato 1 from fridge 1`  
   You pick up the tomato 1 from the fridge 1.

**25.** `> go to sinkbasin 1`  
   You arrive at sinkbasin 1. On the sinkbasin 1, you see a fork 2.

**26.** `> clean tomato 1 with sinkbasin 1`  
   You clean the tomato 1 using the sinkbasin 1.

**27.** `> go to countertop 1`  
   You arrive at countertop 1. On the countertop 1, you see a bread 1, a butterknife 1, a dishsponge 1, a fork 1, a knife 1, a mug 3, a pan 1, a peppershaker 2, a saltshaker 2, a saltshaker 1, a soapbottle 1, and a spoon 2.

**28.** `> move tomato 1 to countertop 1`  
   You move the tomato 1 to the countertop 1.

## Outcome

**WON** after 28 steps.

*What it shows:* Clean task where the manual does not help: the agent runs in circles (`go to diningtable 1` is invalid six times in a row) before it finds the tomato, and still wins in 28 steps. C won the same game in 10.

Same game played by C (no memory): won in 10 steps.
