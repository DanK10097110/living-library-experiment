# Third-party material

| File | Source (pinned commit) | License |
| --- | --- | --- |
| `react_alfworld_3prompts.json` | [ysymyth/ReAct](https://github.com/ysymyth/ReAct) `prompts/alfworld_3prompts.json` @ `6bdb3a1fd38b8188fc7ba4102969fe483df8fdc9` | MIT (`LICENSE-ReAct`) |
| `verl_agent_alfworld_prompt.py` | [langfengQ/verl-agent](https://github.com/langfengQ/verl-agent) `agent_system/environments/prompts/alfworld.py` @ `20bd331bdbc9026a5668e11362178e10ab7400c8` | Apache-2.0 (header in file) |

Reviewed, not vendored: [haotiansun14/AdaPlanner](https://github.com/haotiansun14/AdaPlanner)
@ `dba187601500e7d91fee5fd786a455aaa7988677` (MIT): code-style ALFWorld plans over a fixed
`Agent` API (`goto`, `take`, `put`, `open_receptacle`, `clean`, `heat`, `cool`, `turn_on`).

ReAct's demonstrations say `put X in/on Y`; this ALFWorld version's command is `move X to Y`,
so callers rewrite that one command when building prompts.
