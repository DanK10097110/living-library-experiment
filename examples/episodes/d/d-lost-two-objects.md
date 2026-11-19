# D: a loss on a two-object task

- Condition: **D**   Kind of task: two objects (`pick_two_obj_and_place`)
- Goal: **put two saltshaker in drawer.**
- Game: `train/pick_two_obj_and_place-SaltShaker-None-Drawer-5/trial_T20190907_151045_928468`
- Source: run=old-study-9b-v1, stream=practice-D-0, position=55, memory_before=28 stored successful practice trajectories
- Outcome: **LOST (step budget of 30 used up)** in 30 steps (1 invalid), 33 model calls, 95,501 tokens

## Memory shown to the actor (D: similar solved practice tasks)

- Solved before: **put two keychain in drawer.** (similarity 0.83)
  ```
  > go to drawer 1
  > open drawer 1
  > go to desk 1
  > take keychain 3 from desk 1
  > go to drawer 1
  > move keychain 3 to drawer 1
  > go to desk 1
  > go to sidetable 1
  > take keychain 1 from sidetable 1
  > go to drawer 1
  > go to sidetable 1
  > go to drawer 1
  > go to drawer 2
  > open drawer 2
  > move keychain 1 to drawer 2
  > close drawer 2
  > go to sidetable 1
  > take keychain 4 from sidetable 1
  > go to drawer 1
  > go to drawer 2
  > open drawer 2
  > move keychain 4 to drawer 2
  ```
- Solved before: **put two pencil in drawer.** (similarity 0.8)
  ```
  > go to desk 1
  > take pencil 1 from desk 1
  > go to drawer 1
  > move pencil 1 to drawer 1
  > go to desk 1
  > take pencil 2 from desk 1
  > go to drawer 1
  > move pencil 2 to drawer 1
  ```
- Solved before: **put some pen on drawer.** (similarity 0.78)
  ```
  > go to desk 1
  > inventory
  > go to drawer 1
  > open drawer 1
  > go to desk 1
  > go to dresser 1
  > take pen 4 from dresser 1
  > go to drawer 1
  > move pen 4 to drawer 1
  ```

## Transcript

Initial observation:

```
-= Welcome to TextWorld, ALFRED! =-

You are in the middle of a room. Looking quickly around you, you see a cabinet 20, a cabinet 19, a cabinet 18, a cabinet 17, a cabinet 16, a cabinet 15, a cabinet 14, a cabinet 13, a cabinet 12, a cabinet 11, a cabinet 10, a cabinet 9, a cabinet 8, a cabinet 7, a cabinet 6, a cabinet 5, a cabinet 4, a cabinet 3, a cabinet 2, a cabinet 1, a coffeemachine 1, a countertop 3, a countertop 2, a countertop 1, a drawer 3, a drawer 2, a drawer 1, a fridge 1, a garbagecan 1, a microwave 1, a shelf 3, a shelf 2, a shelf 1, a sinkbasin 1, a stoveburner 4, a stoveburner 3, a stoveburner 2, a stoveburner 1, and a toaster 1.

Your task is to: put two saltshaker in drawer.
```

**1.** `> go to countertop 1`  
   You arrive at countertop 1. On the countertop 1, you see a fork 3, a fork 2, a mug 1, a pan 2, a saltshaker 1, a spatula 1, and a statue 2.

**2.** `> take saltshaker 1 from countertop 1`  
   You pick up the saltshaker 1 from the countertop 1.

**3.** `> go to drawer 1`  
   You arrive at drawer 1. The drawer 1 is closed.

**4.** `> open drawer 1`  
   You open the drawer 1. The drawer 1 is open. In it, you see a knife 1.

**5.** `> move saltshaker 1 to drawer 1`  
   You move the saltshaker 1 to the drawer 1.

**6.** `> go to countertop 2`  
   You arrive at countertop 2. On the countertop 2, you see a bowl 2, a butterknife 1, a fork 1, a knife 2, a ladle 1, a lettuce 1, a mug 2, a peppershaker 2, a spoon 1, a statue 1, and a vase 3.

**7.** `> go to countertop 1`  
   You arrive at countertop 1. On the countertop 1, you see a fork 3, a fork 2, a mug 1, a pan 2, a spatula 1, and a statue 2.

**8.** `> go to countertop 2`  
   You arrive at countertop 2. On the countertop 2, you see a bowl 2, a butterknife 1, a fork 1, a knife 2, a ladle 1, a lettuce 1, a mug 2, a peppershaker 2, a spoon 1, a statue 1, and a vase 3.

**9.** `> go to cabinet 1`  
   You arrive at cabinet 1. The cabinet 1 is closed.

**10.** `> open cabinet 1`  
   You open the cabinet 1. The cabinet 1 is open. In it, you see nothing.

**11.** `> go to countertop 2`  
   You arrive at countertop 2. On the countertop 2, you see a bowl 2, a butterknife 1, a fork 1, a knife 2, a ladle 1, a lettuce 1, a mug 2, a peppershaker 2, a spoon 1, a statue 1, and a vase 3.

**12.** `> go to countertop 1`  
   You arrive at countertop 1. On the countertop 1, you see a fork 3, a fork 2, a mug 1, a pan 2, a spatula 1, and a statue 2.

**13.** `> go to cabinet 1`  
   You arrive at cabinet 1. The cabinet 1 is open. In it, you see nothing.

**14.** `> go to cabinet 2`  **[invalid action]**  
   You arrive at cabinet 1. The cabinet 1 is open. In it, you see nothing.

**15.** `> examine cabinet 2`  
   The cabinet 2 is closed.

**16.** `> open cabinet 2`  
   You open the cabinet 2. The cabinet 2 is open. In it, you see nothing.

**17.** `> go to countertop 2`  
   You arrive at countertop 2. On the countertop 2, you see a bowl 2, a butterknife 1, a fork 1, a knife 2, a ladle 1, a lettuce 1, a mug 2, a peppershaker 2, a spoon 1, a statue 1, and a vase 3.

**18.** `> go to drawer 1`  
   You arrive at drawer 1. The drawer 1 is open. In it, you see a knife 1, and a saltshaker 1.

**19.** `> take saltshaker 1 from drawer 1`  
   You pick up the saltshaker 1 from the drawer 1.

**20.** `> move saltshaker 1 to drawer 1`  
   You move the saltshaker 1 to the drawer 1.

**21.** `> go to drawer 2`  
   You arrive at drawer 2. The drawer 2 is closed.

**22.** `> open drawer 2`  
   You open the drawer 2. The drawer 2 is open. In it, you see a dishsponge 3.

**23.** `> go to countertop 2`  
   You arrive at countertop 2. On the countertop 2, you see a bowl 2, a butterknife 1, a fork 1, a knife 2, a ladle 1, a lettuce 1, a mug 2, a peppershaker 2, a spoon 1, a statue 1, and a vase 3.

**24.** `> go to drawer 2`  
   You arrive at drawer 2. The drawer 2 is open. In it, you see a dishsponge 3.

**25.** `> go to countertop 2`  
   You arrive at countertop 2. On the countertop 2, you see a bowl 2, a butterknife 1, a fork 1, a knife 2, a ladle 1, a lettuce 1, a mug 2, a peppershaker 2, a spoon 1, a statue 1, and a vase 3.

**26.** `> go to cabinet 1`  
   You arrive at cabinet 1. The cabinet 1 is open. In it, you see nothing.

**27.** `> go to countertop 2`  
   You arrive at countertop 2. On the countertop 2, you see a bowl 2, a butterknife 1, a fork 1, a knife 2, a ladle 1, a lettuce 1, a mug 2, a peppershaker 2, a spoon 1, a statue 1, and a vase 3.

**28.** `> go to cabinet 1`  
   You arrive at cabinet 1. The cabinet 1 is open. In it, you see nothing.

**29.** `> go to countertop 2`  
   You arrive at countertop 2. On the countertop 2, you see a bowl 2, a butterknife 1, a fork 1, a knife 2, a ladle 1, a lettuce 1, a mug 2, a peppershaker 2, a spoon 1, a statue 1, and a vase 3.

**30.** `> go to cabinet 1`  
   You arrive at cabinet 1. The cabinet 1 is open. In it, you see nothing.

## Outcome

**LOST** after 30 steps.

*What it shows:* The agent takes one saltshaker and puts it in the drawer in 5 steps, then wanders between countertops/cabinets and never finds the second.
