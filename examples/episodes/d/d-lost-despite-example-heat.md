# D: a loss despite stored heat examples

- Condition: **D**   Kind of task: heat then place (`pick_heat_then_place_in_recep`)
- Goal: **put a hot cup in countertop.**
- Game: `train/pick_heat_then_place_in_recep-Cup-None-CounterTop-17/trial_T20190908_130923_081236`
- Source: run=old-study-9b-v1, stream=practice-D-0, position=44, memory_before=25 stored successful practice trajectories
- Outcome: **LOST (step budget of 30 used up)** in 30 steps (2 invalid), 33 model calls, 92,255 tokens

## Memory shown to the actor (D: similar solved practice tasks)

- Solved before: **cool some tomato and put it in microwave.** (similarity 0.82)
  ```
  > go to countertop 1
  > go to cabinet 1
  > open cabinet 1
  > go to drawer 1
  > open drawer 1
  > go to cabinet 2
  > open cabinet 2
  > go to drawer 1
  > go to drawer 2
  > go to drawer 3
  > open drawer 3
  > go to drawer 4
  > go to cabinet 3
  > open cabinet 3
  > go to countertop 1
  > go to countertop 2
  > take tomato 1 from countertop 2
  > go to fridge 1
  > open fridge 1
  > cool tomato 1 with fridge 1
  > go to microwave 1
  > open microwave 1
  > move tomato 1 to microwave 1
  ```
- Solved before: **cool some bread and put it in countertop.** (similarity 0.82)
  ```
  > go to countertop 1
  > take bread 1 from countertop 1
  > go to fridge 1
  > open fridge 1
  > cool bread 1 with fridge 1
  > close fridge 1
  > go to countertop 1
  > move bread 1 to countertop 1
  ```
- Solved before: **put a hot mug in cabinet.** (similarity 0.81)
  ```
  > go to countertop 1
  > take mug 1 from countertop 1
  > go to stoveburner 1
  > examine stoveburner 1
  > examine stoveburner 1
  > examine stoveburner 1
  > examine stoveburner 1
  > examine stoveburner 1
  > examine stoveburner 1
  > examine stoveburner 1
  > examine mug 1
  > go to microwave 1
  > heat mug 1 with microwave 1
  > go to cabinet 1
  > open cabinet 1
  > move mug 1 to cabinet 1
  ```

## Transcript

Initial observation:

```
-= Welcome to TextWorld, ALFRED! =-

You are in the middle of a room. Looking quickly around you, you see a cabinet 20, a cabinet 19, a cabinet 18, a cabinet 17, a cabinet 16, a cabinet 15, a cabinet 14, a cabinet 13, a cabinet 12, a cabinet 11, a cabinet 10, a cabinet 9, a cabinet 8, a cabinet 7, a cabinet 6, a cabinet 5, a cabinet 4, a cabinet 3, a cabinet 2, a cabinet 1, a coffeemachine 1, a countertop 2, a countertop 1, a diningtable 2, a diningtable 1, a drawer 6, a drawer 5, a drawer 4, a drawer 3, a drawer 2, a drawer 1, a fridge 1, a garbagecan 1, a microwave 1, a sinkbasin 1, a stoveburner 4, a stoveburner 3, a stoveburner 2, a stoveburner 1, and a toaster 1.

Your task is to: put a hot cup in countertop.
```

**1.** `> go to countertop 1`  
   You arrive at countertop 1. On the countertop 1, you see a dishsponge 2, a kettle 1, a knife 2, a lettuce 1, a saltshaker 2, a soapbottle 1, a spatula 1, a spoon 2, a spoon 1, and a spraybottle 1.

**2.** `> go to drawer 1`  
   You arrive at drawer 1. On the drawer 1, you see a dishsponge 3.

**3.** `> go to drawer 2`  
   You arrive at drawer 2. On the drawer 2, you see nothing.

**4.** `> go to drawer 3`  
   You arrive at drawer 3. On the drawer 3, you see nothing.

**5.** `> go to cabinet 1`  
   You arrive at cabinet 1. On the cabinet 1, you see nothing.

**6.** `> go to cabinet 2`  
   You arrive at cabinet 2. On the cabinet 2, you see nothing.

**7.** `> go to cabinet 3`  **[invalid action]**  
   You arrive at cabinet 2. On the cabinet 2, you see nothing.

**8.** `> go to cabinet 3`  **[invalid action]**  
   You arrive at cabinet 2. On the cabinet 2, you see nothing.

**9.** `> go to cabinet 4`  
   You arrive at cabinet 4. On the cabinet 4, you see a dishsponge 1.

**10.** `> go to cabinet 5`  
   You arrive at cabinet 5. The cabinet 5 is closed.

**11.** `> go to cabinet 6`  
   You arrive at cabinet 6. The cabinet 6 is closed.

**12.** `> open cabinet 6`  
   You open the cabinet 6. The cabinet 6 is open. In it, you see nothing.

**13.** `> go to countertop 1`  
   You arrive at countertop 1. On the countertop 1, you see a dishsponge 2, a kettle 1, a knife 2, a lettuce 1, a saltshaker 2, a soapbottle 1, a spatula 1, a spoon 2, a spoon 1, and a spraybottle 1.

**14.** `> go to cabinet 1`  
   You arrive at cabinet 1. On the cabinet 1, you see nothing.

**15.** `> go to drawer 1`  
   You arrive at drawer 1. On the drawer 1, you see a dishsponge 3.

**16.** `> go to drawer 2`  
   You arrive at drawer 2. On the drawer 2, you see nothing.

**17.** `> go to drawer 3`  
   You arrive at drawer 3. On the drawer 3, you see nothing.

**18.** `> go to drawer 4`  
   You arrive at drawer 4. On the drawer 4, you see nothing.

**19.** `> go to fridge 1`  
   You arrive at fridge 1. The fridge 1 is closed.

**20.** `> go to diningtable 1`  
   You arrive at diningtable 1. On the diningtable 1, you see a bread 1, a cellphone 1, a fork 1, a glassbottle 1, a knife 1, a mug 1, a soapbottle 2, and a spatula 2.

**21.** `> go to fridge 1`  
   You arrive at fridge 1. The fridge 1 is closed.

**22.** `> go to diningtable 1`  
   You arrive at diningtable 1. On the diningtable 1, you see a bread 1, a cellphone 1, a fork 1, a glassbottle 1, a knife 1, a mug 1, a soapbottle 2, and a spatula 2.

**23.** `> go to fridge 1`  
   You arrive at fridge 1. The fridge 1 is closed.

**24.** `> go to countertop 1`  
   You arrive at countertop 1. On the countertop 1, you see a dishsponge 2, a kettle 1, a knife 2, a lettuce 1, a saltshaker 2, a soapbottle 1, a spatula 1, a spoon 2, a spoon 1, and a spraybottle 1.

**25.** `> go to diningtable 1`  
   You arrive at diningtable 1. On the diningtable 1, you see a bread 1, a cellphone 1, a fork 1, a glassbottle 1, a knife 1, a mug 1, a soapbottle 2, and a spatula 2.

**26.** `> go to fridge 1`  
   You arrive at fridge 1. The fridge 1 is closed.

**27.** `> go to countertop 1`  
   You arrive at countertop 1. On the countertop 1, you see a dishsponge 2, a kettle 1, a knife 2, a lettuce 1, a saltshaker 2, a soapbottle 1, a spatula 1, a spoon 2, a spoon 1, and a spraybottle 1.

**28.** `> go to diningtable 1`  
   You arrive at diningtable 1. On the diningtable 1, you see a bread 1, a cellphone 1, a fork 1, a glassbottle 1, a knife 1, a mug 1, a soapbottle 2, and a spatula 2.

**29.** `> go to countertop 1`  
   You arrive at countertop 1. On the countertop 1, you see a dishsponge 2, a kettle 1, a knife 2, a lettuce 1, a saltshaker 2, a soapbottle 1, a spatula 1, a spoon 2, a spoon 1, and a spraybottle 1.

**30.** `> go to diningtable 1`  
   You arrive at diningtable 1. On the diningtable 1, you see a bread 1, a cellphone 1, a fork 1, a glassbottle 1, a knife 1, a mug 1, a soapbottle 2, and a spatula 2.

## Outcome

**LOST** after 30 steps.

*What it shows:* A heat task that D could not solve: it searches cabinets, drawers and the fridge for 30 steps without finding the cup or heating it, even though D memory holds a solved heat task.
