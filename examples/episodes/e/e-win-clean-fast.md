# E: clean task won in 6 steps (C needed 18)

- Condition: **E**   Kind of task: clean then place (`pick_clean_then_place_in_recep`)
- Goal: **put a clean butterknife in diningtable.**
- Game: `valid_seen/pick_clean_then_place_in_recep-ButterKnife-None-DiningTable-16/trial_T20190909_114508_617301`
- Source: run=check-e, stream=development-E-11, position=68, library=check-e practice library, frozen (22 entries)
- Outcome: **WON** in 6 steps (0 invalid), 8 model calls, 21,004 tokens

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

1. clean the butterknife 2 with sinkbasin 1
2. move the clean butterknife 2 to diningtable 1

## Transcript

Initial observation:

```
-= Welcome to TextWorld, ALFRED! =-

You are in the middle of a room. Looking quickly around you, you see a cabinet 27, a cabinet 26, a cabinet 25, a cabinet 24, a cabinet 23, a cabinet 22, a cabinet 21, a cabinet 20, a cabinet 19, a cabinet 18, a cabinet 17, a cabinet 16, a cabinet 15, a cabinet 14, a cabinet 13, a cabinet 12, a cabinet 11, a cabinet 10, a cabinet 9, a cabinet 8, a cabinet 7, a cabinet 6, a cabinet 5, a cabinet 4, a cabinet 3, a cabinet 2, a cabinet 1, a coffeemachine 1, a countertop 2, a countertop 1, a diningtable 1, a drawer 12, a drawer 11, a drawer 10, a drawer 9, a drawer 8, a drawer 7, a drawer 6, a drawer 5, a drawer 4, a drawer 3, a drawer 2, a drawer 1, a fridge 1, a garbagecan 1, a microwave 1, a sinkbasin 1, a stoveburner 4, a stoveburner 3, a stoveburner 2, a stoveburner 1, and a toaster 1.

Your task is to: put a clean butterknife in diningtable.
```

**1.** `> go to countertop 1`  
   You arrive at countertop 1. On the countertop 1, you see a butterknife 2, a houseplant 2, a houseplant 1, a ladle 2, a pan 2, a pan 1, a peppershaker 2, a pot 2, a pot 1, a potato 2, a potato 1, a saltshaker 1, and a soapbottle 1.

**2.** `> take butterknife 2 from countertop 1`  
   You pick up the butterknife 2 from the countertop 1.

**3.** `> go to sinkbasin 1`  
   You arrive at sinkbasin 1. On the sinkbasin 1, you see a apple 3, a apple 2, a cup 3, a knife 2, and a spoon 1.

**4.** `> clean butterknife 2 with sinkbasin 1`  
   You clean the butterknife 2 using the sinkbasin 1.

**5.** `> go to diningtable 1`  
   You arrive at diningtable 1. On the diningtable 1, you see a bowl 2, a bowl 1, a bread 1, a butterknife 1, a dishsponge 1, a glassbottle 1, a ladle 1, a lettuce 2, a lettuce 1, a mug 1, a papertowelroll 1, a peppershaker 1, a plate 2, a tomato 1, a winebottle 2, and a winebottle 1.

**6.** `> move butterknife 2 to diningtable 1`  
   You move the butterknife 2 to the diningtable 1.

## Outcome

**WON** after 6 steps.

*What it shows:* Rules shown: the clean Success Process (search the object's location, clean with the sinkbasin, move to target), a rule about opening containers and a location tip. The planner writes only 2 subgoals (clean, move) and the actor goes countertop 1 -> take -> sinkbasin -> clean -> diningtable -> move.

Same game played by C (no memory): won in 18 steps.
