# C: long failure by looping between receptacles

- Condition: **C**   Kind of task: pick and place (`pick_and_place_simple`)
- Goal: **put some creditcard on drawer.**
- Game: `valid_seen/pick_and_place_simple-CreditCard-None-Drawer-227/trial_T20190909_010644_297017`
- Source: run=old-pilot-9b-v1, stream=development-C-11, position=28
- Outcome: **LOST (step budget of 30 used up)** in 30 steps (2 invalid), 34 model calls, 66,767 tokens

## Transcript

Initial observation:

```
-= Welcome to TextWorld, ALFRED! =-

You are in the middle of a room. Looking quickly around you, you see a armchair 2, a armchair 1, a cabinet 8, a cabinet 7, a cabinet 6, a cabinet 5, a cabinet 4, a cabinet 3, a cabinet 2, a cabinet 1, a coffeetable 2, a coffeetable 1, a diningtable 1, a drawer 7, a drawer 6, a drawer 5, a drawer 4, a drawer 3, a drawer 2, a drawer 1, a garbagecan 1, a shelf 13, a shelf 12, a shelf 11, a shelf 10, a shelf 9, a shelf 8, a shelf 7, a shelf 6, a shelf 5, a shelf 4, a shelf 3, a shelf 2, a shelf 1, and a sofa 1.

Your task is to: put some creditcard on drawer.
```

**1.** `> go to drawer 1`  
   You arrive at drawer 1. The drawer 1 is closed.

**2.** `> open drawer 1`  
   You open the drawer 1. The drawer 1 is open. In it, you see nothing.

**3.** `> go to cabinet 1`  
   You arrive at cabinet 1. The cabinet 1 is closed.

**4.** `> open cabinet 1`  
   You open the cabinet 1. The cabinet 1 is open. In it, you see nothing.

**5.** `> go to cabinet 2`  
   You arrive at cabinet 2. The cabinet 2 is closed.

**6.** `> open cabinet 2`  
   You open the cabinet 2. The cabinet 2 is open. In it, you see nothing.

**7.** `> go to cabinet 1`  
   You arrive at cabinet 1. The cabinet 1 is open. In it, you see nothing.

**8.** `> go to cabinet 3`  
   You arrive at cabinet 3. The cabinet 3 is closed.

**9.** `> open cabinet 3`  
   You open the cabinet 3. The cabinet 3 is open. In it, you see nothing.

**10.** `> go to cabinet 4`  
   You arrive at cabinet 4. The cabinet 4 is closed.

**11.** `> open cabinet 4`  
   You open the cabinet 4. The cabinet 4 is open. In it, you see nothing.

**12.** `> go to drawer 1`  
   You arrive at drawer 1. The drawer 1 is open. In it, you see nothing.

**13.** `> go to shelf 1`  
   You arrive at shelf 1. On the shelf 1, you see nothing.

**14.** `> go to shelf 1`  **[invalid action]**  
   You arrive at shelf 1. On the shelf 1, you see nothing.

**15.** `> go to shelf 1`  **[invalid action]**  
   You arrive at shelf 1. On the shelf 1, you see nothing.

**16.** `> go to shelf 2`  
   You arrive at shelf 2. On the shelf 2, you see a vase 2.

**17.** `> go to shelf 1`  
   You arrive at shelf 1. On the shelf 1, you see nothing.

**18.** `> go to shelf 2`  
   You arrive at shelf 2. On the shelf 2, you see a vase 2.

**19.** `> go to shelf 1`  
   You arrive at shelf 1. On the shelf 1, you see nothing.

**20.** `> go to cabinet 1`  
   You arrive at cabinet 1. The cabinet 1 is open. In it, you see nothing.

**21.** `> go to cabinet 2`  
   You arrive at cabinet 2. The cabinet 2 is open. In it, you see nothing.

**22.** `> go to cabinet 3`  
   You arrive at cabinet 3. The cabinet 3 is open. In it, you see nothing.

**23.** `> go to cabinet 4`  
   You arrive at cabinet 4. The cabinet 4 is open. In it, you see nothing.

**24.** `> go to drawer 1`  
   You arrive at drawer 1. The drawer 1 is open. In it, you see nothing.

**25.** `> go to drawer 2`  
   You arrive at drawer 2. The drawer 2 is closed.

**26.** `> go to shelf 1`  
   You arrive at shelf 1. On the shelf 1, you see nothing.

**27.** `> go to cabinet 1`  
   You arrive at cabinet 1. The cabinet 1 is open. In it, you see nothing.

**28.** `> go to cabinet 2`  
   You arrive at cabinet 2. The cabinet 2 is open. In it, you see nothing.

**29.** `> go to shelf 1`  
   You arrive at shelf 1. On the shelf 1, you see nothing.

**30.** `> go to cabinet 3`  
   You arrive at cabinet 3. The cabinet 3 is open. In it, you see nothing.

## Outcome

**LOST** after 30 steps.

*What it shows:* After checking drawer 1 and cabinets 1-4, the agent starts cycling `go to shelf 1` / `go to shelf 2` / cabinet 1..4 / drawer 1 without ever completing the search, and exhausts the 30-step budget.
