# D: a two-object win that is messy but succeeds

- Condition: **D**   Kind of task: two objects (`pick_two_obj_and_place`)
- Goal: **put two alarmclock in shelf.**
- Game: `train/pick_two_obj_and_place-AlarmClock-None-Shelf-316/trial_T20190909_010429_853588`
- Source: run=old-study-9b-v1, stream=practice-D-0, position=8, memory_before=4 stored successful practice trajectories
- Outcome: **WON** in 17 steps (6 invalid), 18 model calls, 42,926 tokens

## Memory shown to the actor (D: similar solved practice tasks)

- Solved before: **put a cd in safe.** (similarity 0.66)
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
- Solved before: **clean some fork and put it in drawer.** (similarity 0.65)
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
- Solved before: **put a clean soapbar in toilet.** (similarity 0.59)
  ```
  > go to cabinet 1
  > go to cabinet 2
  > open cabinet 2
  > go to cabinet 3
  > open cabinet 3
  > go to drawer 1
  > go to drawer 2
  > go to sinkbasin 1
  > go to countertop 1
  > go to countertop 2
  > take soapbar 3 from countertop 2
  > go to sinkbasin 1
  > clean soapbar 3 with sinkbasin 1
  > go to toilet 1
  > move soapbar 3 to toilet 1
  ```

## Transcript

Initial observation:

```
-= Welcome to TextWorld, ALFRED! =-

You are in the middle of a room. Looking quickly around you, you see a bed 1, a desk 1, a drawer 2, a drawer 1, a garbagecan 1, a shelf 1, and a sidetable 1.

Your task is to: put two alarmclock in shelf.
```

**1.** `> go to desk 1`  
   You arrive at desk 1. On the desk 1, you see a alarmclock 2, a alarmclock 1, a book 1, a bowl 2, a cellphone 2, a cellphone 1, a creditcard 1, a desklamp 1, a houseplant 1, a keychain 1, a pen 2, a pen 1, and a pencil 1.

**2.** `> take alarmclock 1 from desk 1`  
   You pick up the alarmclock 1 from the desk 1.

**3.** `> go to desk 1`  **[invalid action]**  
   You pick up the alarmclock 1 from the desk 1.

**4.** `> go to desk 1`  **[invalid action]**  
   You pick up the alarmclock 1 from the desk 1.

**5.** `> go to desk 1`  **[invalid action]**  
   You pick up the alarmclock 1 from the desk 1.

**6.** `> examine desk 1`  
   On the desk 1, you see a alarmclock 2, a book 1, a bowl 2, a cellphone 2, a cellphone 1, a creditcard 1, a desklamp 1, a houseplant 1, a keychain 1, a pen 2, a pen 1, and a pencil 1.

**7.** `> take alarmclock 2 from desk 1`  **[invalid action]**  
   On the desk 1, you see a alarmclock 2, a book 1, a bowl 2, a cellphone 2, a cellphone 1, a creditcard 1, a desklamp 1, a houseplant 1, a keychain 1, a pen 2, a pen 1, and a pencil 1.

**8.** `> go to desk 1`  **[invalid action]**  
   On the desk 1, you see a alarmclock 2, a book 1, a bowl 2, a cellphone 2, a cellphone 1, a creditcard 1, a desklamp 1, a houseplant 1, a keychain 1, a pen 2, a pen 1, and a pencil 1.

**9.** `> move alarmclock 1 to desk 1`  
   You move the alarmclock 1 to the desk 1.

**10.** `> take alarmclock 2 from desk 1`  
   You pick up the alarmclock 2 from the desk 1.

**11.** `> go to shelf 1`  
   You arrive at shelf 1. On the shelf 1, you see nothing.

**12.** `> move alarmclock 2 to shelf 1`  
   You move the alarmclock 2 to the shelf 1.

**13.** `> think: The task is complete.`  **[invalid action]**  
   You move the alarmclock 2 to the shelf 1.

**14.** `> go to desk 1`  
   You arrive at desk 1. On the desk 1, you see a alarmclock 1, a book 1, a bowl 2, a cellphone 2, a cellphone 1, a creditcard 1, a desklamp 1, a houseplant 1, a keychain 1, a pen 2, a pen 1, and a pencil 1.

**15.** `> take alarmclock 1 from desk 1`  
   You pick up the alarmclock 1 from the desk 1.

**16.** `> go to shelf 1`  
   You arrive at shelf 1. On the shelf 1, you see a alarmclock 2.

**17.** `> move alarmclock 1 to shelf 1`  
   You move the alarmclock 1 to the shelf 1.

## Outcome

**WON** after 17 steps.

*What it shows:* Six retrievals of stored trajectories happen in this game (one per subgoal). The agent still produces several invalid commands (a `think:` line, `take alarmclock 2` before it is reachable) but finishes in 17 steps.
