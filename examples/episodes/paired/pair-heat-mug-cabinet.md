# Heat a mug: C stuck at the stoveburner, E uses the microwave

Same game, two conditions: **C lost, E won**.

Goal: **put a hot mug in cabinet.**   Kind: heat then place

*What it shows:* C picks the mug up and tries to put it on the stoveburner (invalid) and examines the burners for 30 steps; E goes straight to the microwave: `heat mug 1 with microwave 1`, then cabinet.

- Only one rule was shown (a Corrected Error about going to the target after heating); the microwave itself came from the planner. The same game with another library (check-avoid70, whose recipe names the microwave) is also won in 8 steps.

---

## Heat a mug: C stuck at the stoveburner, E uses the microwave (C)

- Condition: **C**   Kind of task: heat then place (`pick_heat_then_place_in_recep`)
- Goal: **put a hot mug in cabinet.**
- Game: `valid_seen/pick_heat_then_place_in_recep-Mug-None-Cabinet-3/trial_T20190909_014639_335717`
- Source: run=old-pilot-9b-v1, stream=development-C-11, position=54
- Outcome: **LOST (step budget of 30 used up)** in 30 steps (3 invalid), 33 model calls, 71,177 tokens

### Transcript

Initial observation:

```
-= Welcome to TextWorld, ALFRED! =-

You are in the middle of a room. Looking quickly around you, you see a cabinet 4, a cabinet 3, a cabinet 2, a cabinet 1, a coffeemachine 1, a countertop 1, a drawer 8, a drawer 7, a drawer 6, a drawer 5, a drawer 4, a drawer 3, a drawer 2, a drawer 1, a fridge 1, a garbagecan 1, a microwave 1, a sidetable 1, a sinkbasin 1, a stoveburner 4, a stoveburner 3, a stoveburner 2, a stoveburner 1, and a toaster 1.

Your task is to: put a hot mug in cabinet.
```

**1.** `> go to coffeemachine 1`  
   You arrive at coffeemachine 1. On the coffeemachine 1, you see a mug 1.

**2.** `> take mug 1 from coffeemachine 1`  
   You pick up the mug 1 from the coffeemachine 1.

**3.** `> go to stoveburner 1`  
   You arrive at stoveburner 1. On the stoveburner 1, you see nothing.

**4.** `> examine stoveburner 1`  
   On the stoveburner 1, you see nothing.

**5.** `> examine stoveburner 1`  
   On the stoveburner 1, you see nothing.

**6.** `> examine stoveburner 2`  
   On the stoveburner 2, you see a kettle 1.

**7.** `> examine stoveburner 1`  
   On the stoveburner 1, you see nothing.

**8.** `> place mug 1 on stoveburner 1`  **[invalid action]**  
   On the stoveburner 1, you see nothing.

**9.** `> examine stoveburner 1`  
   On the stoveburner 1, you see nothing.

**10.** `> examine stoveburner 1`  
   On the stoveburner 1, you see nothing.

**11.** `> examine stoveburner 1`  
   On the stoveburner 1, you see nothing.

**12.** `> examine stoveburner 1`  
   On the stoveburner 1, you see nothing.

**13.** `> place mug 1 on stoveburner 1`  **[invalid action]**  
   On the stoveburner 1, you see nothing.

**14.** `> examine stoveburner 1`  
   On the stoveburner 1, you see nothing.

**15.** `> inventory`  
   You are carrying: a mug 1.

**16.** `> place mug 1 on stoveburner 2`  **[invalid action]**  
   You are carrying: a mug 1.

**17.** `> examine stoveburner 2`  
   On the stoveburner 2, you see a kettle 1.

**18.** `> examine stoveburner 2`  
   On the stoveburner 2, you see a kettle 1.

**19.** `> examine stoveburner 2`  
   On the stoveburner 2, you see a kettle 1.

**20.** `> examine stoveburner 2`  
   On the stoveburner 2, you see a kettle 1.

**21.** `> examine stoveburner 2`  
   On the stoveburner 2, you see a kettle 1.

**22.** `> examine stoveburner 2`  
   On the stoveburner 2, you see a kettle 1.

**23.** `> examine stoveburner 2`  
   On the stoveburner 2, you see a kettle 1.

**24.** `> examine stoveburner 2`  
   On the stoveburner 2, you see a kettle 1.

**25.** `> examine stoveburner 2`  
   On the stoveburner 2, you see a kettle 1.

**26.** `> examine stoveburner 2`  
   On the stoveburner 2, you see a kettle 1.

**27.** `> go to cabinet 1`  
   You arrive at cabinet 1. The cabinet 1 is closed.

**28.** `> go to stoveburner 2`  
   You arrive at stoveburner 2. On the stoveburner 2, you see a kettle 1.

**29.** `> examine stoveburner 2`  
   On the stoveburner 2, you see a kettle 1.

**30.** `> examine stoveburner 2`  
   On the stoveburner 2, you see a kettle 1.

### Outcome

**LOST** after 30 steps.


---

## Heat a mug: C stuck at the stoveburner, E uses the microwave (E)

- Condition: **E**   Kind of task: heat then place (`pick_heat_then_place_in_recep`)
- Goal: **put a hot mug in cabinet.**
- Game: `valid_seen/pick_heat_then_place_in_recep-Mug-None-Cabinet-3/trial_T20190909_014639_335717`
- Source: run=check-e, stream=development-E-11, position=54, library=check-e practice library, frozen (22 entries)
- Outcome: **WON** in 8 steps (0 invalid), 9 model calls, 19,988 tokens

### Rules shown to planner and actor

- `rule_16` **Corrected Error**, kind `pick_heat_then_place_in_recep`, Beta(3,2) mean 0.6
  > When the object must be heated and placed in a receptacle, go to the target receptacle after heating instead of trying to place it on a stoveburner.
  > Example: The agent failed by placing the potato on stoveburner 1 and stoveburner 2, then succeeded by moving it to diningtable 1 after heating it with the microwave.

### Planner subgoals

1. find a mug
2. heat the mug in the microwave
3. put the hot mug in a cabinet

### Transcript

Initial observation:

```
-= Welcome to TextWorld, ALFRED! =-

You are in the middle of a room. Looking quickly around you, you see a cabinet 4, a cabinet 3, a cabinet 2, a cabinet 1, a coffeemachine 1, a countertop 1, a drawer 8, a drawer 7, a drawer 6, a drawer 5, a drawer 4, a drawer 3, a drawer 2, a drawer 1, a fridge 1, a garbagecan 1, a microwave 1, a sidetable 1, a sinkbasin 1, a stoveburner 4, a stoveburner 3, a stoveburner 2, a stoveburner 1, and a toaster 1.

Your task is to: put a hot mug in cabinet.
```

**1.** `> go to countertop 1`  
   You arrive at countertop 1. On the countertop 1, you see a bowl 2, a bread 2, a bread 1, a cup 3, a dishsponge 3, a dishsponge 2, a dishsponge 1, a houseplant 1, a knife 1, a lettuce 2, a mug 2, a mug 1, a peppershaker 3, a peppershaker 2, a potato 1, a saltshaker 1, a spatula 1, a spoon 3, a spoon 2, and a winebottle 1.

**2.** `> take mug 1 from countertop 1`  
   You pick up the mug 1 from the countertop 1.

**3.** `> go to microwave 1`  
   You arrive at microwave 1. The microwave 1 is closed.

**4.** `> open microwave 1`  
   You open the microwave 1. The microwave 1 is open. In it, you see nothing.

**5.** `> heat mug 1 with microwave 1`  
   You heat the mug 1 using the microwave 1.

**6.** `> go to cabinet 1`  
   You arrive at cabinet 1. The cabinet 1 is closed.

**7.** `> open cabinet 1`  
   You open the cabinet 1. The cabinet 1 is open. In it, you see a plate 2, and a plate 1.

**8.** `> move mug 1 to cabinet 1`  
   You move the mug 1 to the cabinet 1.

### Outcome

**WON** after 8 steps.
