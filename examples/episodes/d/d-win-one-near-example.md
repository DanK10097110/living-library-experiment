# D: a win with a partly relevant example

- Condition: **D**   Kind of task: pick and place (`pick_and_place_simple`)
- Goal: **put a statue in coffeetable.**
- Game: `train/pick_and_place_simple-Statue-None-CoffeeTable-201/trial_T20190908_124733_145874`
- Source: run=old-study-9b-v1, stream=practice-D-0, position=10, memory_before=5 stored successful practice trajectories
- Outcome: **WON** in 13 steps (0 invalid), 14 model calls, 28,811 tokens

## Memory shown to the actor (D: similar solved practice tasks)

- Solved before: **put a statue in sidetable.** (similarity 0.78)
  ```
  > go to sidetable 1
  > go to shelf 1
  > go to shelf 2
  > take statue 3 from shelf 2
  > go to sidetable 1
  > move statue 3 to sidetable 1
  ```
- Solved before: **clean some fork and put it in drawer.** (similarity 0.59)
  ```
  > go to diningtable 1
  > go to sinkbasin 1
  > go to diningtable 1
  > take fork 1 from diningtable 1
  > go to sinkbasin 1
  > clean fork 1 with sinkbasin 1
  > go to drawer 1
  > move fork 1 to drawer 1
  ```
- Solved before: **put a cd in safe.** (similarity 0.58)
  ```
  > go to safe 1
  > open safe 1
  > go to drawer 1
  > open drawer 1
  > go to drawer 2
  > open drawer 2
  > go to drawer 3
  > open drawer 3
  > open drawer 4
  > take cd 2 from drawer 4
  > go to safe 1
  > move cd 2 to safe 1
  ```

## Transcript

Initial observation:

```
-= Welcome to TextWorld, ALFRED! =-

You are in the middle of a room. Looking quickly around you, you see a armchair 2, a armchair 1, a coffeetable 1, a diningtable 2, a diningtable 1, a drawer 2, a drawer 1, a garbagecan 1, a sidetable 2, a sidetable 1, a sofa 1, and a tvstand 1.

Your task is to: put a statue in coffeetable.
```

**1.** `> go to coffeetable 1`  
   You arrive at coffeetable 1. On the coffeetable 1, you see a bowl 1, a newspaper 1, and a pencil 2.

**2.** `> go to diningtable 1`  
   You arrive at diningtable 1. On the diningtable 1, you see a houseplant 1.

**3.** `> go to drawer 1`  
   You arrive at drawer 1. The drawer 1 is closed.

**4.** `> open drawer 1`  
   You open the drawer 1. The drawer 1 is open. In it, you see a pencil 3.

**5.** `> go to diningtable 1`  
   You arrive at diningtable 1. On the diningtable 1, you see a houseplant 1.

**6.** `> go to drawer 2`  
   You arrive at drawer 2. The drawer 2 is closed.

**7.** `> open drawer 2`  
   You open the drawer 2. The drawer 2 is open. In it, you see nothing.

**8.** `> go to diningtable 1`  
   You arrive at diningtable 1. On the diningtable 1, you see a houseplant 1.

**9.** `> go to armchair 1`  
   You arrive at armchair 1. On the armchair 1, you see a keychain 2, a keychain 1, and a remotecontrol 1.

**10.** `> go to tvstand 1`  
   You arrive at tvstand 1. On the tvstand 1, you see a creditcard 2, a keychain 3, a statue 1, a television 1, a tissuebox 1, and a watch 2.

**11.** `> take statue 1 from tvstand 1`  
   You pick up the statue 1 from the tvstand 1.

**12.** `> go to coffeetable 1`  
   You arrive at coffeetable 1. On the coffeetable 1, you see a bowl 1, a newspaper 1, and a pencil 2.

**13.** `> move statue 1 to coffeetable 1`  
   You move the statue 1 to the coffeetable 1.

## Outcome

**WON** after 13 steps.

*What it shows:* Goal "put a statue in coffeetable" with an earlier statue game in memory. The agent still searches 10 steps (the statue is on the tvstand), so the memory did not tell it where the object is, only how the task is done.
