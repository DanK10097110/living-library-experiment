"""What still holds of the 2026-11-20 design review after the redesign of the same day (LIBRARY-SPEC.md): the
Builder's view (the same for E and E-minus), Corrected Error shape, the end-of-batch near-duplicate merge, and a
replay == live check of batched E practice. The mechanisms the redesign removed (text freeze exceptions, base
rates and lift, hidden guesses, votes, folds) lost their tests with them."""
import copy
import inspect
import json
from pathlib import Path
import tempfile
import unittest

from living_library import manual
from living_library.agents import Agent
from living_library.config import Settings
from living_library.environments import MiniWorld, demo_manifest
from living_library.models import FixtureModel, ModelResponse

try:
    from living_library.embedding import LexicalEmbedding
except ImportError:      # before the code-skill library removal is merged
    from living_library.library import LexicalEmbedding

NEW_AGENT = 'library' not in inspect.signature(Agent).parameters
LOOK = 'look_at_obj_in_light'
PICK = 'pick'
TASK = {'object': 'apple 1', 'target': 'cabinet 1', 'task_type': PICK}
TIP = 'If a container is closed, open it before looking inside.'


def rule(i, kind, text, task_type=LOOK, **extra):
    return {**manual.new_rule(f'rule_{i}', kind, text, '', task_type), **extra}


def quiet(*args, **kwargs):
    pass


class Judging(FixtureModel):
    """The fixture policy; the per-rule judge says not followed; the Builder answers `operations` and records
    what it was shown."""
    def __init__(self, operations=()):
        self.operations, self.builder_rules = list(operations), []

    def complete(self, role, payload, seed, context):
        if role == 'judge':
            return ModelResponse({'followed': 'no', 'usefulness': 0, 'reason': 'fixture'})
        if role == 'builder' and 'game' in payload:
            self.builder_rules.append([r['id'] for r in payload['rules']])
            return ModelResponse({'diagnosis': 'imperfect rules', 'operations': copy.deepcopy(self.operations)})
        return super().complete(role, payload, seed, context)


class BuilderView(unittest.TestCase):
    def library(self, n=30):
        # rules 1-9 match the goal "put some apple in cabinet" best (a new rule is ranked by its text)
        return [rule(i, 'Special Phenomenon', f'When you put some apple in cabinet, check spot {i}.' if i < 10 else
                     f'When cleaning, try place {chr(96 + i % 26)}{i}.', PICK) for i in range(1, n + 1)]

    @unittest.skipUnless(NEW_AGENT, 'needs the agent without the code-skill library (merged branch)')
    def test_e_and_e_minus_builders_see_the_same_relevant_and_newest_rules(self):
        seen = {}
        for condition in ('E', 'E-minus'):
            model = Judging()
            Agent(Settings(), condition, model, LexicalEmbedding(), MiniWorld, rules=self.library()).run(
                TASK, 1, {'phase': 'practice', 'position': 0})
            seen[condition] = model.builder_rules[0]
        self.assertEqual(seen['E'], seen['E-minus'])
        self.assertEqual(len(seen['E']), manual.BUILDER_SEES)
        self.assertTrue({'rule_29', 'rule_30'} <= set(seen['E']))           # the newest two

    def test_for_builder_ranks_by_relevance_and_adds_the_newest(self):
        rules = self.library(30) + [rule(31, 'Unresolved Error', 'When looking, nothing happened.', PICK)]
        view = [r['id'] for r in manual.for_builder(rules, PICK, manual.BUILDER_SEES, 'put some apple in cabinet',
                                                    LexicalEmbedding().similarity)]
        self.assertEqual(len(view), manual.BUILDER_SEES)
        self.assertTrue({'rule_30', 'rule_31'} <= set(view))                # the newest two (a note included)
        self.assertTrue({f'rule_{i}' for i in range(1, 10)} <= set(view))   # keyed by this game's task
        small = manual.for_builder(rules[:5], PICK, manual.BUILDER_SEES, 'x', LexicalEmbedding().similarity)
        self.assertEqual(len(small), 5)


class CorrectedErrorShape(unittest.TestCase):
    def test_a_corrected_error_may_not_list_steps(self):
        recipe_like = 'When heating: take the object, go to the microwave, heat it, then put it in the target.'
        self.assertIn('lists steps (only a Success Process may)', manual.rule_problems('Corrected Error', recipe_like))
        self.assertEqual(manual.rule_problems('Corrected Error', 'When the target is closed, open it instead of '
                                              'putting the object on top.'), [])
        self.assertEqual(manual.rule_problems('Success Process', recipe_like), [])


class BatchDedupe(unittest.TestCase):
    def test_new_near_duplicates_of_a_batch_merge_into_the_older_rule(self):
        old = rule(1, 'Special Phenomenon', TIP, sources=[{'task': 'a'}])
        old['ev']['followed'] = 3
        new1 = {**rule(2, 'Special Phenomenon', TIP.replace('looking', 'peeking')), 'sources': [{'task': 'b'}]}
        new2 = rule(3, 'Special Phenomenon', 'If a target is full, use another one.')
        new3 = rule(4, 'Special Phenomenon', TIP.replace('inside', 'in'))
        rules = [old, new1, new2, new3]
        live = copy.deepcopy(rules)
        ops = manual.batch_dedupe(rules, ['rule_1'], LexicalEmbedding().similarity)
        self.assertEqual([(o['id'], o['absorbed']) for o in ops], [('rule_1', 'rule_2'), ('rule_1', 'rule_4')])
        self.assertEqual([r['id'] for r in rules], ['rule_1', 'rule_3'])
        self.assertEqual((rules[0]['ev']['followed'], rules[0]['rule'], rules[0]['sources']),
                         (3, TIP, [{'task': 'a'}, {'task': 'b'}]))
        self.assertEqual(manual.replay(live, ops, []), rules)


class Rephrasing(Judging):
    """A Builder that writes a near-copy of one tip in every won game (lexically ~0.9 similar), so games of one
    batch write near-duplicates that only the end-of-batch merge can catch."""
    WORDS = ('now', 'first', 'always', 'carefully', 'quickly', 'again', 'there', 'then')

    def complete(self, role, payload, seed, context):
        if role == 'builder' and 'game' in payload:
            word = self.WORDS[context.get('position', 0) % len(self.WORDS)] if isinstance(context, dict) else 'now'
            self.operations = [{'op': 'write_rule', 'type': 'Special Phenomenon', 'scope': 'all',
                                'rule': f'When a container is closed, open it before putting the object inside {word}.'}]
        return super().complete(role, payload, seed, context)


@unittest.skipUnless(NEW_AGENT, 'needs the experiment without the code-skill library (merged branch)')
class BatchedReplayEqualsLive(unittest.TestCase):
    def test_batched_e_practice_replays_exactly_with_the_new_rules(self):
        from living_library.experiment import Runner, load_json
        cfg = Settings(practice_episodes=6, evaluation_games=2, step_budget=15, bootstrap_samples=20,
                       practice_batch=3, seeds=[11])
        with tempfile.TemporaryDirectory() as tmp:
            runner = Runner(cfg, demo_manifest(), tmp, model=Rephrasing(), embedder=LexicalEmbedding(), probe=False)
            runner.study(('E',), demo_count=6, log=quiet)
            root = Path(tmp) / 'checkpoints' / f'practice-E-{cfg.practice_seed}'
            saved = [load_json(p) for p in sorted(root.glob('*.json'))]
        self.assertEqual(len(saved), 6)
        memories, k, kinds = [], cfg.practice_batch, []
        for position, checkpoint in enumerate(saved):
            live = memories[position - 1] if position else []
            start = position - position % k
            base = memories[start - 1] if start else []
            ops = checkpoint['record']['manual']['operations']
            kinds += [op['op'] for op in ops]
            got = json.loads(json.dumps(manual.replay(live, ops, [], base)))
            self.assertEqual(got, checkpoint['memory']['rules'], f'game {position}')
            memories.append(checkpoint['memory']['rules'])
        self.assertIn('dedupe', kinds)                       # the end-of-batch merge ran and is replayable
        self.assertIn('outcome', kinds)
        texts = [r['rule'] for r in memories[-1] if r['type'] == 'Special Phenomenon']
        self.assertEqual(len(texts), 1, texts)               # near-copies of one batch merged into one rule


if __name__ == '__main__':
    unittest.main()
