# C: a look-at-object win that looks accidental

- Condition: **C**   Kind of task: look at object under a lamp (`look_at_obj_in_light`)
- Goal: **examine the bowl with the desklamp.**
- Game: `valid_seen/look_at_obj_in_light-Bowl-None-DeskLamp-316/trial_T20190908_230702_962704`
- Source: run=old-pilot-9b-v1, stream=development-C-11, position=66
- Outcome: **WON** in 14 steps (0 invalid), 15 model calls, 32,522 tokens

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

**3.** `> move bowl 1 to desk 1`  
   You move the bowl 1 to the desk 1.

**4.** `> use desklamp 1`  
   You turn on the desklamp 1.

**5.** `> examine desk 1`  
   On the desk 1, you see a alarmclock 1, a bowl 1, a cd 2, a cd 1, a cellphone 1, a desklamp 1, a houseplant 1, a keychain 2, a keychain 1, and a pen 1.

**6.** `> examine desk 1`  
   On the desk 1, you see a alarmclock 1, a bowl 1, a cd 2, a cd 1, a cellphone 1, a desklamp 1, a houseplant 1, a keychain 2, a keychain 1, and a pen 1.

**7.** `> examine desk 1`  
   On the desk 1, you see a alarmclock 1, a bowl 1, a cd 2, a cd 1, a cellphone 1, a desklamp 1, a houseplant 1, a keychain 2, a keychain 1, and a pen 1.

**8.** `> examine desk 1`  
   On the desk 1, you see a alarmclock 1, a bowl 1, a cd 2, a cd 1, a cellphone 1, a desklamp 1, a houseplant 1, a keychain 2, a keychain 1, and a pen 1.

**9.** `> examine desk 1`  
   On the desk 1, you see a alarmclock 1, a bowl 1, a cd 2, a cd 1, a cellphone 1, a desklamp 1, a houseplant 1, a keychain 2, a keychain 1, and a pen 1.

**10.** `> examine desk 1`  
   On the desk 1, you see a alarmclock 1, a bowl 1, a cd 2, a cd 1, a cellphone 1, a desklamp 1, a houseplant 1, a keychain 2, a keychain 1, and a pen 1.

**11.** `> examine desk 1`  
   On the desk 1, you see a alarmclock 1, a bowl 1, a cd 2, a cd 1, a cellphone 1, a desklamp 1, a houseplant 1, a keychain 2, a keychain 1, and a pen 1.

**12.** `> use desklamp 1`  
   You turn on the desklamp 1.

**13.** `> examine desk 1`  
   On the desk 1, you see a alarmclock 1, a bowl 1, a cd 2, a cd 1, a cellphone 1, a desklamp 1, a houseplant 1, a keychain 2, a keychain 1, and a pen 1.

**14.** `> take bowl 1 from desk 1`  
   You pick up the bowl 1 from the desk 1.

## Outcome

**WON** after 14 steps.

*What it shows:* Take the bowl, put it back, `use desklamp 1`, then examine the desk eight times in a row and finally take the bowl again, which is what completes the goal.
