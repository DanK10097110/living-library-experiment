# Clean a cloth: C grabs a towel and never recovers, E finds the cloth

Same game, two conditions: **C lost, E won**.

Goal: **put a clean cloth in cabinet.**   Kind: clean then place

*What it shows:* C walks to the towelholder, takes a towel (not a cloth), tries `clean towel` (invalid) and loops on invalid moves. E, shown "scan the bathtubbasin and countertops first", goes to the bathtubbasin, finds cloth 2 and finishes in 7 steps.


---

## Clean a cloth: C grabs a towel and never recovers, E finds the cloth (C)

- Condition: **C**   Kind of task: clean then place (`pick_clean_then_place_in_recep`)
- Goal: **put a clean cloth in cabinet.**
- Game: `valid_seen/pick_clean_then_place_in_recep-Cloth-None-Cabinet-405/trial_T20190907_080903_889497`
- Source: run=old-pilot-9b-v1, stream=development-C-11, position=22
- Outcome: **LOST (step budget of 30 used up)** in 30 steps (13 invalid), 34 model calls, 74,254 tokens

### Transcript

Initial observation:

```
-= Welcome to TextWorld, ALFRED! =-

You are in the middle of a room. Looking quickly around you, you see a bathtubbasin 1, a cabinet 5, a cabinet 4, a cabinet 3, a cabinet 2, a cabinet 1, a countertop 1, a garbagecan 1, a handtowelholder 2, a handtowelholder 1, a sinkbasin 1, a toilet 1, a toiletpaperhanger 1, and a towelholder 1.

Your task is to: put a clean cloth in cabinet.
```

**1.** `> go to towelholder 1`  
   You arrive at towelholder 1. On the towelholder 1, you see a towel 1.

**2.** `> take towel 1 from towelholder 1`  
   You pick up the towel 1 from the towelholder 1.

**3.** `> go to sinkbasin 1`  
   You arrive at sinkbasin 1. On the sinkbasin 1, you see nothing.

**4.** `> clean towel 1 with sinkbasin 1`  **[invalid action]**  
   You arrive at sinkbasin 1. On the sinkbasin 1, you see nothing.

**5.** `> move towel 1 to cabinet 1`  **[invalid action]**  
   You arrive at sinkbasin 1. On the sinkbasin 1, you see nothing.

**6.** `> examine sinkbasin 1`  
   On the sinkbasin 1, you see nothing.

**7.** `> move towel 1 to cabinet 1`  **[invalid action]**  
   On the sinkbasin 1, you see nothing.

**8.** `> inventory`  
   You are carrying: a towel 1.

**9.** `> move towel 1 to sinkbasin 1`  **[invalid action]**  
   You are carrying: a towel 1.

**10.** `> move towel 1 to sinkbasin 1`  **[invalid action]**  
   You are carrying: a towel 1.

**11.** `> move towel 1 to sinkbasin 1`  **[invalid action]**  
   You are carrying: a towel 1.

**12.** `> examine towel 1`  
   There's nothing special about towel 1.

**13.** `> move towel 1 to sinkbasin 1`  **[invalid action]**  
   There's nothing special about towel 1.

**14.** `> examine sinkbasin 1`  
   On the sinkbasin 1, you see nothing.

**15.** `> examine towel 1`  
   There's nothing special about towel 1.

**16.** `> move towel 1 to cabinet 1`  **[invalid action]**  
   There's nothing special about towel 1.

**17.** `> go to cabinet 1`  
   You arrive at cabinet 1. The cabinet 1 is closed.

**18.** `> open cabinet 1`  
   You open the cabinet 1. The cabinet 1 is open. In it, you see a soapbottle 2, and a soapbottle 1.

**19.** `> examine towel 1`  
   There's nothing special about towel 1.

**20.** `> go to sinkbasin 1`  
   You arrive at sinkbasin 1. On the sinkbasin 1, you see nothing.

**21.** `> move towel 1 to sinkbasin 1`  **[invalid action]**  
   You arrive at sinkbasin 1. On the sinkbasin 1, you see nothing.

**22.** `> examine towel 1`  
   There's nothing special about towel 1.

**23.** `> move towel 1 to cabinet 1`  **[invalid action]**  
   There's nothing special about towel 1.

**24.** `> move towel 1 to sinkbasin 1`  **[invalid action]**  
   There's nothing special about towel 1.

**25.** `> examine sinkbasin 1`  
   On the sinkbasin 1, you see nothing.

**26.** `> examine towel 1`  
   There's nothing special about towel 1.

**27.** `> go to cabinet 1`  
   You arrive at cabinet 1. The cabinet 1 is open. In it, you see a soapbottle 2, and a soapbottle 1.

**28.** `> examine towel 1`  
   There's nothing special about towel 1.

**29.** `> move towel 1 to cabinet 1`  **[invalid action]**  
   There's nothing special about towel 1.

**30.** `> move towel 1 to cabinet 1`  **[invalid action]**  
   There's nothing special about towel 1.

### Outcome

**LOST** after 30 steps.


---

## Clean a cloth: C grabs a towel and never recovers, E finds the cloth (E)

- Condition: **E**   Kind of task: clean then place (`pick_clean_then_place_in_recep`)
- Goal: **put a clean cloth in cabinet.**
- Game: `valid_seen/pick_clean_then_place_in_recep-Cloth-None-Cabinet-405/trial_T20190907_080903_889497`
- Source: run=check-e, stream=development-E-11, position=22, library=check-e practice library, frozen (22 entries)
- Outcome: **WON** in 7 steps (0 invalid), 8 model calls, 18,288 tokens

### Rules shown to planner and actor

- `rule_1` **Success Process**, kind `pick_clean_then_place_in_recep`, Beta(6,3) mean 0.67
  > When an object must be cleaned and placed: search the object's current location first, clean it with the sinkbasin, then move it to the target location.
  > Example: go to bathtubbasin 1, take cloth 1 from bathtubbasin 1, go to sinkbasin 1, clean cloth 1 with sinkbasin 1, go to toilet 1, move cloth 1 to toilet 1
- `rule_2` **Special Phenomenon**, kind `pick_clean_then_place_in_recep`, Beta(6,3) mean 0.67
  > When placing an object in a container, the container must be opened before moving the object inside.
  > Example: go to cabinet 1, open cabinet 1, move winebottle 2 to cabinet 1
- `rule_9` **Corrected Error**, kind `pick_clean_then_place_in_recep`, Beta(1,1) mean 0.5
  > When the target object must be found, never open cabinets or drawers first; scan the bathtubbasin and countertops first.
  > Example: Agent wasted time opening multiple cabinets without finding the cloth, which was in the bathtubbasin.

### Planner subgoals

1. go to bathtubbasin 1 and find the cloth
2. take the cloth from bathtubbasin 1
3. go to sinkbasin 1 and clean the cloth
4. go to cabinet 1 and open it
5. put the clean cloth in cabinet 1

### Transcript

Initial observation:

```
-= Welcome to TextWorld, ALFRED! =-

You are in the middle of a room. Looking quickly around you, you see a bathtubbasin 1, a cabinet 5, a cabinet 4, a cabinet 3, a cabinet 2, a cabinet 1, a countertop 1, a garbagecan 1, a handtowelholder 2, a handtowelholder 1, a sinkbasin 1, a toilet 1, a toiletpaperhanger 1, and a towelholder 1.

Your task is to: put a clean cloth in cabinet.
```

**1.** `> go to bathtubbasin 1`  
   You arrive at bathtubbasin 1. On the bathtubbasin 1, you see a cloth 2, and a soapbar 1.

**2.** `> take cloth 2 from bathtubbasin 1`  
   You pick up the cloth 2 from the bathtubbasin 1.

**3.** `> go to sinkbasin 1`  
   You arrive at sinkbasin 1. On the sinkbasin 1, you see nothing.

**4.** `> clean cloth 2 with sinkbasin 1`  
   You clean the cloth 2 using the sinkbasin 1.

**5.** `> go to cabinet 1`  
   You arrive at cabinet 1. The cabinet 1 is closed.

**6.** `> open cabinet 1`  
   You open the cabinet 1. The cabinet 1 is open. In it, you see a soapbottle 2, and a soapbottle 1.

**7.** `> move cloth 2 to cabinet 1`  
   You move the cloth 2 to the cabinet 1.

### Outcome

**WON** after 7 steps.
