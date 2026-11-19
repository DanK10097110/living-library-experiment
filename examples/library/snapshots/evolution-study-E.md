# How the study E library evolved, game by game

Run `study`, stream `practice-E-0` (current code, 24 workers; frozen at the first 35 practice games). Per game: did the first attempt win, how many rules the manual has afterwards (visible / total), which rule ids were added or changed.

| game | goal | 1st attempt | rules (visible/total) | added | changed |
|---|---|---|---|---|---|
| 0 | clean some fork and put it in drawer. | won | 1/2 | rule_1, rule_2 | - |
| 1 | put a cloth in drawer. | lost | 1/4 | rule_3, rule_4 | - |
| 2 | put two spatula in drawer. | lost | 1/6 | rule_5, rule_6 | - |
| 3 | put a cd in safe. | won | 2/7 | rule_7 | - |
| 4 | put a hot mug in coffeemachine. | lost | 2/8 | rule_8 | - |
| 5 | put a statue in sidetable. | won | 2/8 | - | - |
| 6 | clean some plate and put it in microwave. | lost | 2/8 | - | - |
| 7 | put a clean soapbar in toilet. | won | 3/9 | rule_9 | - |
| 8 | put two alarmclock in shelf. | won | 5/11 | rule_10, rule_11 | - |
| 9 | put a cellphone in dresser. | lost | 6/11 | - | rule_3, rule_7 |
| 10 | put a statue in coffeetable. | won | 6/11 | - | rule_7 |
| 11 | put a keychain in desk. | won | 6/11 | - | rule_7 |
| 12 | put a cool bowl in cabinet. | lost | 8/14 | rule_12, rule_13, rule_14 | - |
| 13 | put a spraybottle in garbagecan. | won | 8/14 | - | rule_7 |
| 14 | put two cellphone in dresser. | lost | 8/14 | - | - |
| 15 | put a clean butterknife in countertop. | won | 8/14 | - | rule_1, rule_9 |
| 16 | put a cool pan in diningtable. | lost | 8/14 | - | rule_12, rule_13 |
| 17 | put some cellphone on dresser. | lost | 8/14 | - | rule_3, rule_7 |
| 18 | clean some cloth and put it in countertop. | won | 8/14 | - | rule_1, rule_9 |
| 19 | cool some plate and put it in cabinet. | lost | 8/14 | - | rule_12, rule_13 |
| 20 | put a hot potato in diningtable. | lost | 9/16 | rule_15, rule_16 | - |
| 21 | put some spraybottle on toilet. | won | 9/16 | - | rule_3, rule_7 |
| 22 | cool some pan and put it in cabinet. | won | 9/16 | - | rule_12, rule_13 |
| 23 | cool some tomato and put it in microwave. | won | 9/16 | - | rule_12, rule_13 |
| 24 | put two keychain in drawer. | lost | 9/16 | - | rule_10, rule_11 |
| 25 | put two pencil in drawer. | won | 9/16 | - | rule_10, rule_11 |
| 26 | put a handtowel in cabinet. | won | 9/16 | - | rule_3, rule_7 |
| 27 | put some pen on drawer. | lost | 9/16 | - | rule_3, rule_7 |
| 28 | put a clean butterknife in sidetable. | won | 9/16 | - | rule_1, rule_9 |
| 29 | clean some fork and put it in drawer. | lost | 9/16 | - | rule_1, rule_9 |
| 30 | cool some bowl and put it in microwave. | lost | 9/16 | - | rule_12, rule_13 |
| 31 | find two cellphone and put them in bed. | lost | 9/16 | - | rule_5, rule_10, rule_11 |
| 32 | cool some bread and put it in countertop. | won | 9/16 | - | rule_12, rule_13 |
| 33 | put a clean pan in stoveburner. | won | 9/16 | - | rule_1, rule_9 |
| 34 | put a laptop in desk. | won | 9/16 | - | rule_3, rule_7 |

## Rule histories

Each line is a point where the rule text, type, visibility or Beta(a,b) changed.

### rule_3

- game 1: [Special Phenomenon] Beta(1,1) HIDDEN: When placing an object in a container, ensure the container is open before attempting to place.
- game 9: [Special Phenomenon] Beta(1,1) visible: When placing an object in a container, ensure the container is open before attempting to place.
- game 17: [Special Phenomenon] Beta(1,2) visible: When placing an object in a container, ensure the container is open before attempting to place.
- game 21: [Special Phenomenon] Beta(2,2) visible: When placing an object on a surface, ensure the surface is open before attempting to place.
- game 26: [Special Phenomenon] Beta(3,2) visible: When placing an object on a surface, ensure the surface is open before attempting to place.
- game 27: [Special Phenomenon] Beta(3,3) visible: When placing an object in a container, ensure the container is open before attempting to place.
- game 34: [Special Phenomenon] Beta(4,3) visible: When placing an object on a surface, no need to open the surface; when placing in a container, ensure the container is open before attempting to place.

### rule_7

- game 3: [Success Process] Beta(1,1) visible: When an object must be picked up and placed: search drawers first, open the target container if closed, take the object, go to the target container, move the object there.
- game 9: [Success Process] Beta(1,2) visible: When an object must be picked up and placed: search the target surface first, open the target container if closed, take the object from the surface, go to the target container, move the object there.
- game 10: [Success Process] Beta(2,2) visible: When an object must be picked up and placed: search drawers first, open the target container if closed, take the object, go to the target container, move the object there.
- game 11: [Success Process] Beta(3,2) visible: When an object must be picked up and placed: search drawers first, open the target container if closed, take the object, go to the target container, move the object there.
- game 13: [Success Process] Beta(4,2) visible: When an object must be picked up and placed: search drawers first, take the object, go to the target container, move the object there.
- game 17: [Success Process] Beta(4,3) visible: When an object must be picked up and placed: search drawers first, take the object, go to the target container, move the object there.
- game 21: [Success Process] Beta(5,3) visible: When an object must be picked up and placed: search cabinets first, take the object, go to the target, move the object there.
- game 26: [Success Process] Beta(6,3) visible: When an object must be picked up and placed: search cabinets first, take the object, go to the target, open the target if closed, move the object there.
- game 27: [Success Process] Beta(6,4) visible: When an object must be picked up and placed: search drawers and containers first, take the object, go to the target, open the target if closed, move the object there.
- game 34: [Success Process] Beta(7,4) visible: When an object must be picked up and placed: search drawers and containers first, take the object, go to the target, move the object there if the target is open or a surface.

### rule_13

- game 12: [Success Process] Beta(1,1) visible: When the object must be cooled and placed in the target: search countertops and dining tables first, take the object, cool it with the fridge, open the target cabinet if closed, move the object there.
- game 16: [Success Process] Beta(1,2) visible: When the object must be cooled and placed in the target: search stoveburners and countertops first, take the object, cool it with the fridge, open the target cabinet if closed, move the object there.
- game 19: [Success Process] Beta(1,3) visible: When the object must be cooled and placed in the target: search stoveburners and countertops first, take the object, cool it with the fridge, open the target cabinet if closed, move the object there.
- game 22: [Success Process] Beta(2,3) visible: When the object must be cooled and placed in the target: search stoveburners and countertops first, take the object, cool it with the fridge, open the target cabinet if closed, move the object there.
- game 23: [Success Process] Beta(3,3) visible: When the object must be cooled and placed in the target: search countertops first, take the object, cool it with the fridge, open the target cabinet if closed, move the object there.
- game 30: [Success Process] Beta(3,4) visible: When the object must be cooled and placed in the target: search cabinets and countertops first, take the object, cool it with the fridge, open the target cabinet if closed, move the object there.
- game 32: [Success Process] Beta(4,4) visible: When an object must be cooled and placed in the target: search cabinets and countertops first, take the object, cool it with the fridge, open the target if closed, move the object there.

### rule_5

- game 2: [Unresolved Error] Beta(1,1) HIDDEN: When placing multiple objects in a container, search all possible locations for the objects before opening any containers.
- game 31: [Unresolved Error] Beta(1,1) HIDDEN: When placing multiple objects in a container, search all possible furniture surfaces before opening any containers.

Note how `rule_7` (the pick-and-place recipe) flips between "search drawers first", "search cabinets first" and "search the target surface first": each won game lets the Builder rewrite the text to what that one game did, so the text follows the last game rather than a stable truth (layout overfitting); the Beta numbers are the only check.
