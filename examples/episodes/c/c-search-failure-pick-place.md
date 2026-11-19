# C: long failure while searching a big room

- Condition: **C**   Kind of task: pick and place (`pick_and_place_simple`)
- Goal: **put some box on dresser.**
- Game: `valid_seen/pick_and_place_simple-Box-None-Dresser-224/trial_T20190907_164104_229696`
- Source: run=old-pilot-9b-v1, stream=development-C-11, position=30
- Outcome: **LOST (step budget of 30 used up)** in 30 steps (1 invalid), 33 model calls, 65,425 tokens

## Transcript

Initial observation:

```
-= Welcome to TextWorld, ALFRED! =-

You are in the middle of a room. Looking quickly around you, you see a armchair 1, a cabinet 1, a drawer 21, a drawer 20, a drawer 19, a drawer 18, a drawer 17, a drawer 16, a drawer 15, a drawer 14, a drawer 13, a drawer 12, a drawer 11, a drawer 10, a drawer 9, a drawer 8, a drawer 7, a drawer 6, a drawer 5, a drawer 4, a drawer 3, a drawer 2, a drawer 1, a dresser 1, a garbagecan 1, a sidetable 5, a sidetable 4, a sidetable 3, a sidetable 2, a sidetable 1, and a sofa 1.

Your task is to: put some box on dresser.
```

**1.** `> go to drawer 1`  
   You arrive at drawer 1. On the drawer 1, you see nothing.

**2.** `> go to cabinet 1`  
   You arrive at cabinet 1. On the cabinet 1, you see nothing.

**3.** `> go to drawer 2`  
   You arrive at drawer 2. The drawer 2 is closed.

**4.** `> open drawer 2`  
   You open the drawer 2. The drawer 2 is open. In it, you see nothing.

**5.** `> go to drawer 3`  
   You arrive at drawer 3. The drawer 3 is closed.

**6.** `> open drawer 3`  
   You open the drawer 3. The drawer 3 is open. In it, you see nothing.

**7.** `> go to drawer 4`  
   You arrive at drawer 4. On the drawer 4, you see nothing.

**8.** `> go to drawer 5`  
   You arrive at drawer 5. The drawer 5 is closed.

**9.** `> open drawer 5`  
   You open the drawer 5. The drawer 5 is open. In it, you see nothing.

**10.** `> go to drawer 6`  
   You arrive at drawer 6. The drawer 6 is closed.

**11.** `> open drawer 6`  
   You open the drawer 6. The drawer 6 is open. In it, you see nothing.

**12.** `> go to cabinet 1`  
   You arrive at cabinet 1. On the cabinet 1, you see nothing.

**13.** `> go to drawer 7`  
   You arrive at drawer 7. The drawer 7 is closed.

**14.** `> open drawer 7`  
   You open the drawer 7. The drawer 7 is open. In it, you see nothing.

**15.** `> go to drawer 8`  **[invalid action]**  
   You open the drawer 7. The drawer 7 is open. In it, you see nothing.

**16.** `> open drawer 8`  
   You open the drawer 8. The drawer 8 is open. In it, you see nothing.

**17.** `> go to dresser 1`  
   You arrive at dresser 1. On the dresser 1, you see a book 1, a cellphone 1, a creditcard 2, a keychain 1, a newspaper 1, a remotecontrol 1, and a television 1.

**18.** `> go to drawer 1`  
   You arrive at drawer 1. On the drawer 1, you see nothing.

**19.** `> go to drawer 2`  
   You arrive at drawer 2. The drawer 2 is open. In it, you see nothing.

**20.** `> go to drawer 9`  
   You arrive at drawer 9. The drawer 9 is closed.

**21.** `> open drawer 9`  
   You open the drawer 9. The drawer 9 is open. In it, you see nothing.

**22.** `> go to drawer 10`  
   You arrive at drawer 10. The drawer 10 is closed.

**23.** `> open drawer 10`  
   You open the drawer 10. The drawer 10 is open. In it, you see nothing.

**24.** `> go to drawer 11`  
   You arrive at drawer 11. The drawer 11 is closed.

**25.** `> open drawer 11`  
   You open the drawer 11. The drawer 11 is open. In it, you see nothing.

**26.** `> go to drawer 12`  
   You arrive at drawer 12. The drawer 12 is closed.

**27.** `> open drawer 12`  
   You open the drawer 12. The drawer 12 is open. In it, you see nothing.

**28.** `> go to drawer 13`  
   You arrive at drawer 13. The drawer 13 is closed.

**29.** `> open drawer 13`  
   You open the drawer 13. The drawer 13 is open. In it, you see nothing.

**30.** `> go to drawer 14`  
   You arrive at drawer 14. The drawer 14 is closed.

## Outcome

**LOST** after 30 steps.

*What it shows:* Opens drawer after drawer (up to drawer 11+) looking for a box; goes to the dresser (the target) then back to searching, and runs out of steps.
