# C: typical clean-then-place win, with a few invalid commands on the way

- Condition: **C**   Kind of task: clean then place (`pick_clean_then_place_in_recep`)
- Goal: **put a clean lettuce in countertop.**
- Game: `valid_seen/pick_clean_then_place_in_recep-Lettuce-None-CounterTop-16/trial_T20190909_051630_092360`
- Source: run=old-pilot-9b-v1, stream=development-C-11, position=3
- Outcome: **WON** in 14 steps (4 invalid), 15 model calls, 41,431 tokens

## Transcript

Initial observation:

```
-= Welcome to TextWorld, ALFRED! =-

You are in the middle of a room. Looking quickly around you, you see a cabinet 27, a cabinet 26, a cabinet 25, a cabinet 24, a cabinet 23, a cabinet 22, a cabinet 21, a cabinet 20, a cabinet 19, a cabinet 18, a cabinet 17, a cabinet 16, a cabinet 15, a cabinet 14, a cabinet 13, a cabinet 12, a cabinet 11, a cabinet 10, a cabinet 9, a cabinet 8, a cabinet 7, a cabinet 6, a cabinet 5, a cabinet 4, a cabinet 3, a cabinet 2, a cabinet 1, a coffeemachine 1, a countertop 2, a countertop 1, a diningtable 1, a drawer 12, a drawer 11, a drawer 10, a drawer 9, a drawer 8, a drawer 7, a drawer 6, a drawer 5, a drawer 4, a drawer 3, a drawer 2, a drawer 1, a fridge 1, a garbagecan 1, a microwave 1, a sinkbasin 1, a stoveburner 4, a stoveburner 3, a stoveburner 2, a stoveburner 1, and a toaster 1.

Your task is to: put a clean lettuce in countertop.
```

**1.** `> go to fridge 1`  
   You arrive at fridge 1. The fridge 1 is closed.

**2.** `> open fridge 1`  
   You open the fridge 1. The fridge 1 is open. In it, you see a plate 3, a potato 1, and a tomato 1.

**3.** `> go to diningtable 1`  
   You arrive at diningtable 1. On the diningtable 1, you see a bowl 3, a bowl 2, a cup 1, a dishsponge 2, a dishsponge 1, a egg 1, a knife 1, a lettuce 2, a lettuce 1, a mug 1, a papertowelroll 1, a plate 1, a spoon 1, and a winebottle 1.

**4.** `> take lettuce 1 from diningtable 1`  
   You pick up the lettuce 1 from the diningtable 1.

**5.** `> go to sinkbasin 1`  
   You arrive at sinkbasin 1. On the sinkbasin 1, you see a apple 3, a apple 2, and a spatula 3.

**6.** `> clean lettuce 1 with sinkbasin 1`  
   You clean the lettuce 1 using the sinkbasin 1.

**7.** `> move lettuce 1 to countertop 1`  **[invalid action]**  
   You clean the lettuce 1 using the sinkbasin 1.

**8.** `> move lettuce 1 to countertop 1`  **[invalid action]**  
   You clean the lettuce 1 using the sinkbasin 1.

**9.** `> move lettuce 1 to sinkbasin 1`  
   You move the lettuce 1 to the sinkbasin 1.

**10.** `> take lettuce 1 from sinkbasin 1`  
   You pick up the lettuce 1 from the sinkbasin 1.

**11.** `> move lettuce 1 to countertop 1`  **[invalid action]**  
   You pick up the lettuce 1 from the sinkbasin 1.

**12.** `> move lettuce 1 to countertop 1`  **[invalid action]**  
   You pick up the lettuce 1 from the sinkbasin 1.

**13.** `> go to countertop 1`  
   You arrive at countertop 1. On the countertop 1, you see a apple 1, a bowl 1, a bread 1, a glassbottle 1, a houseplant 2, a houseplant 1, a pan 1, a saltshaker 1, and a winebottle 2.

**14.** `> move lettuce 1 to countertop 1`  
   You move the lettuce 1 to the countertop 1.

## Outcome

**WON** after 14 steps.

*What it shows:* A won clean task (14 steps). The agent cleans the lettuce at the sinkbasin correctly, then wastes 4 steps on `move lettuce to countertop` before it has walked to the countertop (invalid), and recovers by itself.

- Invalid commands answer "Nothing happens." and still cost a step of the 30-step budget.
