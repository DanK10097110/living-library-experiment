# C: typical two-object win (19 steps)

- Condition: **C**   Kind of task: two objects (`pick_two_obj_and_place`)
- Goal: **find two book and put them in desk.**
- Game: `valid_seen/pick_two_obj_and_place-Book-None-Desk-302/trial_T20190906_181233_363875`
- Source: run=old-pilot-9b-v1, stream=development-C-11, position=12
- Outcome: **WON** in 19 steps (0 invalid), 21 model calls, 42,952 tokens

## Transcript

Initial observation:

```
-= Welcome to TextWorld, ALFRED! =-

You are in the middle of a room. Looking quickly around you, you see a bed 1, a desk 1, a drawer 3, a drawer 2, a drawer 1, a garbagecan 1, a safe 1, a shelf 5, a shelf 4, a shelf 3, a shelf 2, a shelf 1, a sidetable 2, and a sidetable 1.

Your task is to: find two book and put them in desk.
```

**1.** `> go to shelf 1`  
   You arrive at shelf 1. On the shelf 1, you see a keychain 3, and a pen 2.

**2.** `> go to drawer 1`  
   You arrive at drawer 1. On the drawer 1, you see nothing.

**3.** `> go to drawer 2`  
   You arrive at drawer 2. The drawer 2 is closed.

**4.** `> open drawer 2`  
   You open the drawer 2. The drawer 2 is open. In it, you see nothing.

**5.** `> go to drawer 3`  
   You arrive at drawer 3. The drawer 3 is closed.

**6.** `> open drawer 3`  
   You open the drawer 3. The drawer 3 is open. In it, you see nothing.

**7.** `> go to shelf 2`  
   You arrive at shelf 2. On the shelf 2, you see a bowl 1, and a creditcard 1.

**8.** `> go to shelf 3`  
   You arrive at shelf 3. On the shelf 3, you see a bowl 2.

**9.** `> go to shelf 4`  
   You arrive at shelf 4. On the shelf 4, you see nothing.

**10.** `> go to shelf 5`  
   You arrive at shelf 5. On the shelf 5, you see a alarmclock 2, a bowl 3, and a houseplant 1.

**11.** `> go to bed 1`  
   You arrive at bed 1. On the bed 1, you see a book 2, a book 1, a pillow 1, and a teddybear 1.

**12.** `> take book 1 from bed 1`  
   You pick up the book 1 from the bed 1.

**13.** `> go to desk 1`  
   You arrive at desk 1. On the desk 1, you see a alarmclock 1, a laptop 1, and a pencil 2.

**14.** `> move book 1 to desk 1`  
   You move the book 1 to the desk 1.

**15.** `> go to shelf 1`  
   You arrive at shelf 1. On the shelf 1, you see a keychain 3, and a pen 2.

**16.** `> go to bed 1`  
   You arrive at bed 1. On the bed 1, you see a book 2, a pillow 1, and a teddybear 1.

**17.** `> take book 2 from bed 1`  
   You pick up the book 2 from the bed 1.

**18.** `> go to desk 1`  
   You arrive at desk 1. On the desk 1, you see a alarmclock 1, a book 1, a laptop 1, and a pencil 2.

**19.** `> move book 2 to desk 1`  
   You move the book 2 to the desk 1.

## Outcome

**WON** after 19 steps.

*What it shows:* Searches shelves and drawers one by one, finds the first book on the bed, carries it to the desk, comes back for the second.
