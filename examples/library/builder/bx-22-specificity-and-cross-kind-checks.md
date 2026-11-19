# The Builder's two deterministic text checks: specific objects, and steps of another kind of task

**What is recorded and what is computed.** The checkpoints store only the final outcome of these checks (a rejection line, or the accepted rule); an accepted rewrite leaves no trace of the original text. So this file (1) runs the current check code (`manual.specific_terms`, `manual.foreign_actions`) on real rule texts and one text quoted from the log, and (2) lists real model rewrite responses taken from the study's model cache (original text not stored there).

## The two checks

1. **Specific objects/rooms** (DECISIONS 2026-11-18): a rule naming a portable object kind (plate, tomato, kettle ...) or "room" gets ONE Builder rewrite ("use the object / the target"); if the rewrite is still specific the rule is rejected and logged.
2. **Steps of another task kind** (DECISIONS 2026-11-19): a rule scoped to one task kind may not contain the action of another kind (clean/cool/heat/lamp/two objects). One rewrite ("remove steps of another kind of task"), else rejected. Appliance names used only as places to search are allowed.

## Check output on real texts

| text source | task kind | specific terms found | foreign actions found | verdict |
|---|---|---|---|---|
| practice-e game 4 (rejected, still specific after the rewrite) | heat then place | kettle | - | rewrite once, else reject |
| check-avoid70 rule_19 (written before the check existed) | cool then place | tomato | - | rewrite once, else reject |
| check-avoid70 rule_14 (before the check) | cool then place | plate | - | rewrite once, else reject |
| practice-e game 38 (rejected: names "room") | look at object under a lamp | room | - | rewrite once, else reject |
| check-e rule_1 (accepted) | clean then place | - | - | ok |
| study incident 2026-11-19 (quoted from results/LOG.md: a cooling recipe that copied a step from the winning game) | cool then place | - | clean | rewrite once, else reject |
| same recipe, appliance only as a place to search (allowed) | cool then place | - | - | ok |
| heat recipe that cools (foreign action) | heat then place | - | cool | rewrite once, else reject |

Texts checked:

- practice-e game 4 (rejected, still specific after the rewrite): _When heating a container to make it hot, never place the target directly on the kettle ..._
- check-avoid70 rule_19 (written before the check existed): _When searching for a tomato to cool, check countertops and fridge contents first before exhaustively opening cabinets and drawers._
- check-avoid70 rule_14 (before the check): _When searching for a cool plate to place in a cabinet, systematically check all countertops first before attempting to retrieve it from the fridge._
- practice-e game 38 (rejected: names "room"): _When an object must be examined with a light: search the current room for the object ..._
- check-e rule_1 (accepted): _When an object must be cleaned and placed: search the object's current location first, clean it with the sinkbasin, then move it to the target location._
- study incident 2026-11-19 (quoted from results/LOG.md: a cooling recipe that copied a step from the winning game): _When an object must be cooled and placed: find and take it, clean it with sinkbasin, cool it with fridge, go to the target, put it there._
- same recipe, appliance only as a place to search (allowed): _When an object must be cooled and placed: search the fridge and countertops, take it, cool it with the fridge, put it in the target._
- heat recipe that cools (foreign action): _When an object must be heated: take it, cool it first, heat it with the microwave, then put it in the target._

## Real rewrite responses from the study model cache

Each is the model's answer to a one-shot "rewrite this rule, general, at most 25 words" request (original text not recorded). All pass the specific-object check.

- When the object must be cooled and placed in the target: search countertops and dining tables first, take the object, cool it with the fridge, open the target cabinet if closed, move the object there.  (specific terms now: none)
- When an object must be picked up and placed: search drawers and containers first, take the object, go to the target, open the target if closed, move the object there.  (specific terms now: none)
- When an object must be cooled and placed, search countertops and cabinets first, then cool with the fridge, open the target if closed, and put it there.  (specific terms now: none)
- When an object must be found and cooled, search countertops first, then cabinets, before opening drawers.  (specific terms now: none)