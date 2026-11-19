# HONEST LOSS: C won in 11 steps, E lost with an Anti-Pattern in the prompt

Same game, two conditions: **C won, E lost**.

Goal: **put some mug on dresser.**   Kind: pick and place

*What it shows:* C goes to the dresser, then countertop, drawers, diningtable and finds the mug in 11 steps. E opens and closes drawer 1, walks around, goes to the dresser (the target) repeatedly and never finds the mug on the diningtable. Rules shown: the recipe and the "do not repeat examine" Anti-Pattern.

- The planner collapsed the task into 3 subgoals including "go to dresser 1" before finding the mug.

---

## HONEST LOSS: C won in 11 steps, E lost with an Anti-Pattern in the prompt (C)

- Condition: **C**   Kind of task: pick and place (`pick_and_place_simple`)
- Goal: **put some mug on dresser.**
- Game: `valid_seen/pick_and_place_simple-Mug-None-Dresser-311/trial_T20190909_152837_739016`
- Source: run=old-pilot-9b-v1, stream=development-C-11, position=63
- Outcome: **WON** in 11 steps (0 invalid), 12 model calls, 21,368 tokens

### Transcript

Initial observation:

```
-= Welcome to TextWorld, ALFRED! =-

You are in the middle of a room. Looking quickly around you, you see a armchair 2, a armchair 1, a bed 1, a countertop 1, a diningtable 1, a drawer 2, a drawer 1, a dresser 1, a garbagecan 1, a laundryhamper 1, and a sidetable 1.

Your task is to: put some mug on dresser.
```

**1.** `> go to dresser 1`  
   You arrive at dresser 1. On the dresser 1, you see a cd 1, a remotecontrol 1, and a television 1.

**2.** `> go to countertop 1`  
   You arrive at countertop 1. On the countertop 1, you see a book 1, a bowl 1, a mirror 1, and a pen 3.

**3.** `> go to drawer 1`  
   You arrive at drawer 1. The drawer 1 is closed.

**4.** `> open drawer 1`  
   You open the drawer 1. The drawer 1 is open. In it, you see a creditcard 3, and a creditcard 2.

**5.** `> go to drawer 2`  
   You arrive at drawer 2. The drawer 2 is closed.

**6.** `> open drawer 2`  
   You open the drawer 2. The drawer 2 is open. In it, you see a creditcard 1, and a remotecontrol 2.

**7.** `> go to countertop 1`  
   You arrive at countertop 1. On the countertop 1, you see a book 1, a bowl 1, a mirror 1, and a pen 3.

**8.** `> go to diningtable 1`  
   You arrive at diningtable 1. On the diningtable 1, you see a alarmclock 1, a cd 2, a cellphone 2, a cellphone 1, a mug 1, and a pen 2.

**9.** `> take mug 1 from diningtable 1`  
   You pick up the mug 1 from the diningtable 1.

**10.** `> go to dresser 1`  
   You arrive at dresser 1. On the dresser 1, you see a cd 1, a remotecontrol 1, and a television 1.

**11.** `> move mug 1 to dresser 1`  
   You move the mug 1 to the dresser 1.

### Outcome

**WON** after 11 steps.


---

## HONEST LOSS: C won in 11 steps, E lost with an Anti-Pattern in the prompt (E)

- Condition: **E**   Kind of task: pick and place (`pick_and_place_simple`)
- Goal: **put some mug on dresser.**
- Game: `valid_seen/pick_and_place_simple-Mug-None-Dresser-311/trial_T20190909_152837_739016`
- Source: run=check-e, stream=development-E-11, position=63, library=check-e practice library, frozen (22 entries)
- Outcome: **LOST (step budget of 30 used up)** in 30 steps (4 invalid), 33 model calls, 64,890 tokens

### Rules shown to planner and actor

- `rule_4` **Success Process**, kind `pick_and_place_simple`, Beta(8,4) mean 0.67
  > When an object must be placed on a target: search the area first, open any closed containers, take the object, go to the target, move the object to the target.
  > Example: search drawer 1, open drawer 1, take watch 1 from drawer 1, go to coffeetable 1, move watch 1 to coffeetable 1
- `rule_18` **Anti-Pattern**, kind `pick_and_place_simple`, Beta(3,1) mean 0.75
  > When examining an appliance, do not issue the same "examine" command again and again.
  > Example: "examine desk", again and again

### Planner subgoals

1. search for a mug in the environment
2. go to dresser 1
3. put the mug on dresser 1

### Transcript

Initial observation:

```
-= Welcome to TextWorld, ALFRED! =-

You are in the middle of a room. Looking quickly around you, you see a armchair 2, a armchair 1, a bed 1, a countertop 1, a diningtable 1, a drawer 2, a drawer 1, a dresser 1, a garbagecan 1, a laundryhamper 1, and a sidetable 1.

Your task is to: put some mug on dresser.
```

**1.** `> go to drawer 1`  
   You arrive at drawer 1. The drawer 1 is closed.

**2.** `> open drawer 1`  
   You open the drawer 1. The drawer 1 is open. In it, you see a creditcard 3, and a creditcard 2.

**3.** `> close drawer 1`  
   You close the drawer 1.

**4.** `> go to drawer 2`  
   You arrive at drawer 2. The drawer 2 is closed.

**5.** `> open drawer 2`  
   You open the drawer 2. The drawer 2 is open. In it, you see a creditcard 1, and a remotecontrol 2.

**6.** `> go to laundryhamper 1`  
   You arrive at laundryhamper 1. On the laundryhamper 1, you see nothing.

**7.** `> go to countertop 1`  
   You arrive at countertop 1. On the countertop 1, you see a book 1, a bowl 1, a mirror 1, and a pen 3.

**8.** `> go to sidetable 1`  
   You arrive at sidetable 1. On the sidetable 1, you see a keychain 1, a pen 1, and a pencil 1.

**9.** `> go to armchair 1`  
   You arrive at armchair 1. On the armchair 1, you see nothing.

**10.** `> go to bed 1`  
   You arrive at bed 1. On the bed 1, you see a cellphone 3, a pillow 3, a pillow 2, and a pillow 1.

**11.** `> go to dresser 1`  
   You arrive at dresser 1. On the dresser 1, you see a cd 1, a remotecontrol 1, and a television 1.

**12.** `> examine dresser 1`  
   On the dresser 1, you see a cd 1, a remotecontrol 1, and a television 1.

**13.** `> go to drawer 1`  
   You arrive at drawer 1. The drawer 1 is closed.

**14.** `> go to cabinet 1`  **[invalid action]**  
   You arrive at drawer 1. The drawer 1 is closed.

**15.** `> open drawer 1`  
   You open the drawer 1. The drawer 1 is open. In it, you see a creditcard 3, and a creditcard 2.

**16.** `> close drawer 1`  
   You close the drawer 1.

**17.** `> go to drawer 2`  
   You arrive at drawer 2. The drawer 2 is open. In it, you see a creditcard 1, and a remotecontrol 2.

**18.** `> go to laundryhamper 1`  
   You arrive at laundryhamper 1. On the laundryhamper 1, you see nothing.

**19.** `> go to cabinet 1`  **[invalid action]**  
   You arrive at laundryhamper 1. On the laundryhamper 1, you see nothing.

**20.** `> examine laundryhamper 1`  
   On the laundryhamper 1, you see nothing.

**21.** `> go to dresser 1`  
   You arrive at dresser 1. On the dresser 1, you see a cd 1, a remotecontrol 1, and a television 1.

**22.** `> go to countertop 1`  
   You arrive at countertop 1. On the countertop 1, you see a book 1, a bowl 1, a mirror 1, and a pen 3.

**23.** `> go to drawer 1`  
   You arrive at drawer 1. The drawer 1 is closed.

**24.** `> go to cabinet 1`  **[invalid action]**  
   You arrive at drawer 1. The drawer 1 is closed.

**25.** `> go to countertop 1`  
   You arrive at countertop 1. On the countertop 1, you see a book 1, a bowl 1, a mirror 1, and a pen 3.

**26.** `> go to cabinet 1`  **[invalid action]**  
   You arrive at countertop 1. On the countertop 1, you see a book 1, a bowl 1, a mirror 1, and a pen 3.

**27.** `> examine countertop 1`  
   On the countertop 1, you see a book 1, a bowl 1, a mirror 1, and a pen 3.

**28.** `> go to drawer 1`  
   You arrive at drawer 1. The drawer 1 is closed.

**29.** `> go to drawer 2`  
   You arrive at drawer 2. The drawer 2 is open. In it, you see a creditcard 1, and a remotecontrol 2.

**30.** `> go to diningtable 1`  
   You arrive at diningtable 1. On the diningtable 1, you see a alarmclock 1, a cd 2, a cellphone 2, a cellphone 1, a mug 1, and a pen 2.

### Outcome

**LOST** after 30 steps.
