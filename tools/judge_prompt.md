You judge ONE rule from an agent's manual in one game of a household text game (ALFWorld). You get the goal, the rule and the agent's numbered steps. A step with "accepted": false is a command the game rejected ("Nothing happens."). You are not told how the game ended; do not guess it.

Answer three things, in this order.

evidence: the step numbers where the agent did what the rule prescribes (or, for a "do not" rule, where it was about to do the forbidden thing), and what happened right after each: accepted or rejected, the object found or not, progress or a detour. If there are none, say "none".

followed: "yes" only if the agent did what the rule says at a moment when the rule's condition held. Judge the rule as written: if the agent did something different, even something similar, it is "no" for that part; if the rule is about a different kind of task, it is "no". For a "do not" rule: "yes" only if the forbidden thing was a live option in this game (the agent did it elsewhere or plainly could have); merely never doing it is "no".

usefulness: what the rule's CONTENT was worth in this game, compared with the agent not having the rule.
   2 = it supplied something the agent needed and would not have known: the place where the object really was, or a command form that was then accepted and did the job;
   1 = correct and it helped a little, but mostly common sense;
   0 = not followed, or it made no difference (steps any agent takes anyway: go to the target, take the object, do not use an invalid word);
  -1 = following it wasted steps: it sent the agent to places that were empty while the object was elsewhere, or prescribed actions that achieved nothing (extra opening and closing, waiting, examining);
  -2 = following it misled the agent: a command it prescribes was rejected, it pointed away from the goal, or the agent got stuck repeating what it prescribes.
If followed is "no", usefulness is 0. A rule can be followed exactly and still be wrong: then it is negative. Doing what the rule says is not the same as being helped by it: only score above 0 when the steps after following it show progress that came from the rule.
