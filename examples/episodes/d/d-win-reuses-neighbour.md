# D: a win helped by a near-identical stored solution

- Condition: **D**   Kind of task: clean then place (`pick_clean_then_place_in_recep`)
- Goal: **put a clean butterknife in sidetable.**
- Game: `train/pick_clean_then_place_in_recep-ButterKnife-None-SideTable-21/trial_T20190907_162153_244284`
- Source: run=old-study-9b-v1, stream=practice-D-0, position=28, memory_before=15 stored successful practice trajectories
- Outcome: **WON** in 6 steps (0 invalid), 8 model calls, 17,991 tokens

## Memory shown to the actor (D: similar solved practice tasks)

- Solved before: **put a clean butterknife in countertop.** (similarity 0.84)
  ```
  > go to drawer 1
  > open drawer 1
  > go to countertop 1
  > take butterknife 1 from countertop 1
  > go to sinkbasin 1
  > clean butterknife 1 with sinkbasin 1
  > go to countertop 1
  > move butterknife 1 to countertop 1
  ```
- Solved before: **cool some tomato and put it in microwave.** (similarity 0.74)
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
- Solved before: **put some spraybottle on toilet.** (similarity 0.73)
  ```
  > go to toilet 1
  > go to cabinet 1
  > take spraybottle 1 from cabinet 1
  > go to toilet 1
  > move spraybottle 1 to toilet 1
  ```

## Transcript

Initial observation:

```
-= Welcome to TextWorld, ALFRED! =-

You are in the middle of a room. Looking quickly around you, you see a cabinet 4, a cabinet 3, a cabinet 2, a cabinet 1, a coffeemachine 1, a countertop 1, a diningtable 3, a diningtable 2, a diningtable 1, a drawer 1, a fridge 1, a garbagecan 1, a microwave 1, a sidetable 1, a sinkbasin 1, a stoveburner 4, a stoveburner 3, a stoveburner 2, a stoveburner 1, and a toaster 1.

Your task is to: put a clean butterknife in sidetable.
```

**1.** `> go to countertop 1`  
   You arrive at countertop 1. On the countertop 1, you see a butterknife 1, a dishsponge 1, a peppershaker 2, and a tomato 1.

**2.** `> take butterknife 1 from countertop 1`  
   You pick up the butterknife 1 from the countertop 1.

**3.** `> go to sinkbasin 1`  
   You arrive at sinkbasin 1. On the sinkbasin 1, you see a apple 1, a potato 2, and a spatula 2.

**4.** `> clean butterknife 1 with sinkbasin 1`  
   You clean the butterknife 1 using the sinkbasin 1.

**5.** `> go to sidetable 1`  
   You arrive at sidetable 1. On the sidetable 1, you see a butterknife 2, a cup 2, a cup 1, a lettuce 3, a potato 1, a saltshaker 1, and a spoon 1.

**6.** `> move butterknife 1 to sidetable 1`  
   You move the butterknife 1 to the sidetable 1.

## Outcome

**WON** after 6 steps.

*What it shows:* Memory D holds 15 solved practice trajectories. The top hit for this goal is "put a clean butterknife in countertop" (similarity 0.84). The agent skips the search the example had to do (drawer 1 first) and goes straight to countertop 1, cleans, and places in 6 steps.

- The other two retrieved examples (a cooling task and a pick-and-place) are only loosely related; the prompt shows all 3.
