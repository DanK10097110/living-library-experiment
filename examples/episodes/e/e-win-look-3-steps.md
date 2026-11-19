# E: look-at-object solved in 3 steps (C needed 14)

- Condition: **E**   Kind of task: look at object under a lamp (`look_at_obj_in_light`)
- Goal: **examine the bowl with the desklamp.**
- Game: `valid_seen/look_at_obj_in_light-Bowl-None-DeskLamp-316/trial_T20190908_230702_962704`
- Source: run=check-e, stream=development-E-11, position=66, library=check-e practice library, frozen (22 entries)
- Outcome: **WON** in 3 steps (0 invalid), 4 model calls, 7,403 tokens

## Rules shown to planner and actor

- `rule_21` **Success Process**, kind `look_at_obj_in_light`, Beta(1,1) mean 0.5
  > When an object must be looked at under a light: search all shelves and desks for the light source, take the object from its location, move it to the light source's location, use the light source, then look.
  > Example: Search shelves/desks for desklamp. Take pencil. Move pencil to desklamp location. Use desklamp. Look.
- `rule_20` **Corrected Error**, kind `look_at_obj_in_light`, Beta(1,1) mean 0.5
  > When an object must be looked at under a light, first locate the light source, then move the object directly under it before attempting to look.
  > Example: In this game, the agent failed by moving the pencil to desk 2 without finding the desklamp. The successful retry found the desklamp on shelf 2, moved the pencil there, turned on the desklamp, and then

## Planner subgoals

1. search all shelves and desks for the desklamp
2. go to the location where the desklamp is found
3. take the bowl from its current location
4. move the bowl to the desklamp location
5. turn on the desklamp
6. examine the bowl with the desklamp

## Transcript

Initial observation:

```
-= Welcome to TextWorld, ALFRED! =-

You are in the middle of a room. Looking quickly around you, you see a bed 1, a desk 1, a drawer 2, a drawer 1, a garbagecan 1, a shelf 1, and a sidetable 1.

Your task is to: examine the bowl with the desklamp.
```

**1.** `> go to desk 1`  
   You arrive at desk 1. On the desk 1, you see a alarmclock 1, a bowl 1, a cd 2, a cd 1, a cellphone 1, a desklamp 1, a houseplant 1, a keychain 2, a keychain 1, and a pen 1.

**2.** `> take bowl 1 from desk 1`  
   You pick up the bowl 1 from the desk 1.

**3.** `> use desklamp 1`  
   You turn on the desklamp 1.

## Outcome

**WON** after 3 steps.

*What it shows:* Plan written by the planner follows the rule (find lamp, take object, bring it to the lamp, turn lamp on). The actor takes the bowl and issues `use desklamp 1`; the game is won on step 3.

Same game played by C (no memory): won in 14 steps.
