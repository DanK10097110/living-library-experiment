# C: the typical heat task, never solved by C

- Condition: **C**   Kind of task: heat then place (`pick_heat_then_place_in_recep`)
- Goal: **heat some apple and put it in diningtable.**
- Game: `valid_seen/pick_heat_then_place_in_recep-Apple-None-DiningTable-26/trial_T20190907_060234_011675`
- Source: run=old-pilot-9b-v1, stream=development-C-11, position=62
- Outcome: **LOST (step budget of 30 used up)** in 30 steps (3 invalid), 34 model calls, 74,319 tokens

## Transcript

Initial observation:

```
-= Welcome to TextWorld, ALFRED! =-

You are in the middle of a room. Looking quickly around you, you see a cabinet 10, a cabinet 9, a cabinet 8, a cabinet 7, a cabinet 6, a cabinet 5, a cabinet 4, a cabinet 3, a cabinet 2, a cabinet 1, a coffeemachine 1, a countertop 2, a countertop 1, a diningtable 2, a diningtable 1, a drawer 3, a drawer 2, a drawer 1, a fridge 1, a garbagecan 1, a microwave 1, a sinkbasin 1, a stoveburner 4, a stoveburner 3, a stoveburner 2, a stoveburner 1, and a toaster 1.

Your task is to: heat some apple and put it in diningtable.
```

**1.** `> go to fridge 1`  
   You arrive at fridge 1. The fridge 1 is closed.

**2.** `> go to diningtable 1`  
   You arrive at diningtable 1. On the diningtable 1, you see a bread 2, a bread 1, a butterknife 2, a dishsponge 1, a fork 1, a potato 1, and a spatula 1.

**3.** `> go to fridge 1`  
   You arrive at fridge 1. The fridge 1 is closed.

**4.** `> open fridge 1`  
   You open the fridge 1. The fridge 1 is open. In it, you see a bowl 1, a cup 1, a egg 1, a lettuce 1, a plate 1, and a tomato 1.

**5.** `> go to cabinet 1`  
   You arrive at cabinet 1. On the cabinet 1, you see nothing.

**6.** `> go to drawer 1`  
   You arrive at drawer 1. The drawer 1 is closed.

**7.** `> open drawer 1`  
   You open the drawer 1. The drawer 1 is open. In it, you see nothing.

**8.** `> go to cabinet 1`  
   You arrive at cabinet 1. On the cabinet 1, you see nothing.

**9.** `> go to diningtable 2`  
   You arrive at diningtable 2. On the diningtable 2, you see a apple 1, a bread 3, a cup 3, a egg 3, a peppershaker 2, a soapbottle 2, and a soapbottle 1.

**10.** `> take apple 1 from diningtable 2`  
   You pick up the apple 1 from the diningtable 2.

**11.** `> go to stoveburner 1`  
   You arrive at stoveburner 1. On the stoveburner 1, you see nothing.

**12.** `> examine stoveburner 1`  
   On the stoveburner 1, you see nothing.

**13.** `> place apple 1 on stoveburner 1`  **[invalid action]**  
   On the stoveburner 1, you see nothing.

**14.** `> examine stoveburner 1`  
   On the stoveburner 1, you see nothing.

**15.** `> examine stoveburner 1`  
   On the stoveburner 1, you see nothing.

**16.** `> go to microwave 1`  
   You arrive at microwave 1. The microwave 1 is closed.

**17.** `> open microwave 1`  
   You open the microwave 1. The microwave 1 is open. In it, you see a egg 2, and a mug 2.

**18.** `> move apple 1 to microwave 1`  
   You move the apple 1 to the microwave 1.

**19.** `> close microwave 1`  
   You close the microwave 1.

**20.** `> open microwave 1`  
   You open the microwave 1. The microwave 1 is open. In it, you see a apple 1, a egg 2, and a mug 2.

**21.** `> close microwave 1`  
   You close the microwave 1.

**22.** `> open microwave 1`  
   You open the microwave 1. The microwave 1 is open. In it, you see a apple 1, a egg 2, and a mug 2.

**23.** `> take apple 1 from microwave 1`  
   You pick up the apple 1 from the microwave 1.

**24.** `> go to stoveburner 1`  
   You arrive at stoveburner 1. On the stoveburner 1, you see nothing.

**25.** `> move apple 1 to stoveburner 1`  **[invalid action]**  
   You arrive at stoveburner 1. On the stoveburner 1, you see nothing.

**26.** `> go to microwave 1`  
   You arrive at microwave 1. The microwave 1 is open. In it, you see a egg 2, and a mug 2.

**27.** `> close microwave 1`  
   You close the microwave 1.

**28.** `> open microwave 1`  
   You open the microwave 1. The microwave 1 is open. In it, you see a egg 2, and a mug 2.

**29.** `> move apple 1 to stoveburner 1`  **[invalid action]**  
   You open the microwave 1. The microwave 1 is open. In it, you see a egg 2, and a mug 2.

**30.** `> move apple 1 to microwave 1`  
   You move the apple 1 to the microwave 1.

## Outcome

**LOST** after 30 steps.

*What it shows:* The agent finds the apple, goes to the stoveburner, tries `place apple on stoveburner` (invalid), examines the burner, then moves the apple into the microwave with `move` and opens/closes the microwave without ever issuing `heat apple with microwave`.
