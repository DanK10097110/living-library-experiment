# E: cool task won in 7 steps (C needed 26)

- Condition: **E**   Kind of task: cool then place (`pick_cool_then_place_in_recep`)
- Goal: **cool some plate and put it in countertop.**
- Game: `valid_seen/pick_cool_then_place_in_recep-Plate-None-CounterTop-1/trial_T20190906_205324_559361`
- Source: run=check-e, stream=development-E-11, position=10, library=check-e practice library, frozen (22 entries)
- Outcome: **WON** in 7 steps (0 invalid), 8 model calls, 20,198 tokens

## Rules shown to planner and actor

- `rule_15` **Success Process**, kind `pick_cool_then_place_in_recep`, Beta(3,3) mean 0.5
  > When an object must be cooled and placed: search for the object first, take it, cool it with the fridge, then move it to the target.
  > Example: The agent found pan 1 on stoveburner 1, took it, cooled it with fridge 1, and moved it to diningtable 1.
- `rule_12` **Corrected Error**, kind `pick_cool_then_place_in_recep`, Beta(1,2) mean 0.33
  > When an object must be picked up and placed, search for the object specifically before systematically checking all cabinets and drawers.
  > Example: The agent found pan 1 on stoveburner 1 instead of opening every cabinet sequentially.

## Planner subgoals

1. search for a plate in the environment
2. go to the fridge to cool the plate
3. move the cooled plate to the countertop

## Transcript

Initial observation:

```
-= Welcome to TextWorld, ALFRED! =-

You are in the middle of a room. Looking quickly around you, you see a cabinet 9, a cabinet 8, a cabinet 7, a cabinet 6, a cabinet 5, a cabinet 4, a cabinet 3, a cabinet 2, a cabinet 1, a coffeemachine 1, a countertop 3, a countertop 2, a countertop 1, a drawer 9, a drawer 8, a drawer 7, a drawer 6, a drawer 5, a drawer 4, a drawer 3, a drawer 2, a drawer 1, a fridge 1, a garbagecan 1, a microwave 1, a shelf 3, a shelf 2, a shelf 1, a sinkbasin 1, a stoveburner 4, a stoveburner 3, a stoveburner 2, a stoveburner 1, and a toaster 1.

Your task is to: cool some plate and put it in countertop.
```

**1.** `> go to countertop 1`  
   You arrive at countertop 1. On the countertop 1, you see a creditcard 3, a pan 1, a papertowelroll 1, a spatula 1, and a winebottle 1.

**2.** `> go to countertop 2`  
   You arrive at countertop 2. On the countertop 2, you see a bread 1, a fork 3, a fork 2, a houseplant 1, a knife 2, a mug 2, a pan 2, a plate 1, a pot 1, and a statue 2.

**3.** `> take plate 1 from countertop 2`  
   You pick up the plate 1 from the countertop 2.

**4.** `> go to fridge 1`  
   You arrive at fridge 1. The fridge 1 is closed.

**5.** `> cool plate 1 with fridge 1`  
   You cool the plate 1 using the fridge 1.

**6.** `> go to countertop 1`  
   You arrive at countertop 1. On the countertop 1, you see a creditcard 3, a pan 1, a papertowelroll 1, a spatula 1, and a winebottle 1.

**7.** `> move plate 1 to countertop 1`  
   You move the plate 1 to the countertop 1.

## Outcome

**WON** after 7 steps.

*What it shows:* Cooling recipe: look for the plate on the countertops, `cool plate 1 with fridge 1`, back to the countertop, move. C needed 26 steps for the same game.

Same game played by C (no memory): won in 26 steps.
