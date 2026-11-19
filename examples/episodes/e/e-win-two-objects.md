# E: two-object task in 6 steps (C needed 13)

- Condition: **E**   Kind of task: two objects (`pick_two_obj_and_place`)
- Goal: **put two cd in drawer.**
- Game: `valid_seen/pick_two_obj_and_place-CD-None-Drawer-304/trial_T20190907_230232_832893`
- Source: run=check-e, stream=development-E-11, position=46, library=check-e practice library, frozen (22 entries)
- Outcome: **WON** in 6 steps (1 invalid), 8 model calls, 15,728 tokens

## Rules shown to planner and actor

- `rule_17` **Success Process**, kind `pick_two_obj_and_place`, Beta(3,2) mean 0.6
  > When placing multiple objects in a target, search all furniture surfaces first, then navigate to the target before each move command.
  > Example: Search countertop 1 for peppershaker 2, go to diningtable 1, move peppershaker 2 to diningtable 1, search countertop 1 for peppershaker 3, go to diningtable 1, move peppershaker 3 to diningtable 1.
- `rule_6` **Special Phenomenon**, kind `pick_two_obj_and_place`, Beta(3,2) mean 0.6
  > When searching for the object, search furniture surfaces first before opening any drawers or cabinets.
  > Example: Agent searched countertop 1 before opening cabinet 2 and cabinet 3.
- `rule_11` **Corrected Error**, kind `pick_two_obj_and_place`, Beta(4,4) mean 0.5
  > When two objects must be placed in a target: search furniture surfaces first, take each object, move it to the target.
  > Example: In the failed attempt, moving while holding the object failed; in the successful retry, the agent went to shelf 1 before moving.

## Planner subgoals

1. find cd 2 on furniture surfaces
2. go to desk 1 where cd 2 is located
3. take cd 2 from desk 1
4. go to drawer 1
5. put cd 2 in drawer 1
6. go to desk 1 to find cd 1
7. put cd 1 in drawer 1

## Transcript

Initial observation:

```
-= Welcome to TextWorld, ALFRED! =-

You are in the middle of a room. Looking quickly around you, you see a bed 2, a bed 1, a desk 1, a drawer 3, a drawer 2, a drawer 1, a garbagecan 1, a laundryhamper 1, and a shelf 1.

Your task is to: put two cd in drawer.
```

**1.** `> go to desk 1`  
   You arrive at desk 1. On the desk 1, you see a alarmclock 1, a bowl 1, a cd 2, a cd 1, a cellphone 2, a cellphone 1, a mug 1, a pen 3, and a pencil 1.

**2.** `> take cd 1 from desk 1`  
   You pick up the cd 1 from the desk 1.

**3.** `> go to drawer 1`  **[invalid action]**  
   You pick up the cd 1 from the desk 1.

**4.** `> move cd 1 to drawer 1`  
   You move the cd 1 to the drawer 1.

**5.** `> take cd 2 from desk 1`  
   You pick up the cd 2 from the desk 1.

**6.** `> move cd 2 to drawer 1`  
   You move the cd 2 to the drawer 1.

## Outcome

**WON** after 6 steps.

*What it shows:* Rules: a recipe plus a special-phenomenon note ("search furniture surfaces first before opening drawers"). The agent finds both CDs on the desk, with one invalid `go to drawer 1` (the drawer was already reachable).

Same game played by C (no memory): won in 13 steps.
