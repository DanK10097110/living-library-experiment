# E: simple task won in 4 steps with an Anti-Pattern rule on screen

- Condition: **E**   Kind of task: pick and place (`pick_and_place_simple`)
- Goal: **put some candle on toilet.**
- Game: `valid_seen/pick_and_place_simple-Candle-None-Toilet-429/trial_T20190908_052232_887934`
- Source: run=check-e, stream=development-E-11, position=45, library=check-e practice library, frozen (22 entries)
- Outcome: **WON** in 4 steps (0 invalid), 5 model calls, 8,046 tokens

## Rules shown to planner and actor

- `rule_4` **Success Process**, kind `pick_and_place_simple`, Beta(8,4) mean 0.67
  > When an object must be placed on a target: search the area first, open any closed containers, take the object, go to the target, move the object to the target.
  > Example: search drawer 1, open drawer 1, take watch 1 from drawer 1, go to coffeetable 1, move watch 1 to coffeetable 1
- `rule_18` **Anti-Pattern**, kind `pick_and_place_simple`, Beta(3,1) mean 0.75
  > When examining an appliance, do not issue the same "examine" command again and again.
  > Example: "examine desk", again and again

## Planner subgoals

1. search the room for a candle
2. go to the toilet
3. put the candle on the toilet

## Transcript

Initial observation:

```
-= Welcome to TextWorld, ALFRED! =-

You are in the middle of a room. Looking quickly around you, you see a bathtubbasin 1, a garbagecan 1, a handtowelholder 1, a shelf 3, a shelf 2, a shelf 1, a sinkbasin 1, a toilet 1, a toiletpaperhanger 1, and a towelholder 1.

Your task is to: put some candle on toilet.
```

**1.** `> go to shelf 1`  
   You arrive at shelf 1. On the shelf 1, you see a candle 1, a soapbar 2, and a soapbar 1.

**2.** `> take candle 1 from shelf 1`  
   You pick up the candle 1 from the shelf 1.

**3.** `> go to toilet 1`  
   You arrive at toilet 1. On the toilet 1, you see a soapbottle 2.

**4.** `> move candle 1 to toilet 1`  
   You move the candle 1 to the toilet 1.

## Outcome

**WON** after 4 steps.

*What it shows:* Two rules are shown: a Success Process and an Anti-Pattern ("When examining an appliance, do not issue the same examine command again and again"). The Anti-Pattern is irrelevant here (the agent never examines anything) but it is shown in every pick-and-place game.

Same game played by C (no memory): won in 8 steps.
