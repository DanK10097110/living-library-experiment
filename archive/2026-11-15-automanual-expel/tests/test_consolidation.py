import copy
import unittest

from living_library.agents import Agent
from living_library.config import Settings
from living_library.consolidation import consolidate, too_specific
from living_library.environments import MiniWorld
from living_library.library import Library, LexicalEmbedding, Skill
from living_library.models import FixtureModel, ModelResponse

TASK = {'object': 'apple 1', 'target': 'cabinet 1'}
START = {'task': TASK, 'actions': []}
HOLDING = {'task': TASK, 'actions': ['take apple 1 from table 1']}


def skill(sid, params, pre, post, body, tests=()):
    s = Skill(sid, sid.split('@')[0].replace('_', ' '), {p: 'entity' for p in params}, pre, post, body)
    s.status, s.tests = 'active', list(tests)
    return s


def library(*skills, meta=None):
    lib = Library(Settings())
    for s in copy.deepcopy(skills):   # fixtures are shared across tests
        lib.skills[s.id] = s
        lib.active[s.name] = s.id
    lib.meta = meta or {}
    return lib


class Curator(FixtureModel):
    def __init__(self, response):
        self.response, self.calls = response, 0

    def complete(self, role, payload, seed, context):
        if role == 'curator':
            self.calls += 1
            return ModelResponse(self.response, 100, 50)
        return super().complete(role, payload, seed, context)


def agent(lib, model=None):
    a = Agent(Settings(), 'E-plus', model or FixtureModel(), lib, LexicalEmbedding(), MiniWorld)
    a.seed, a.context = 1, {'position': 24}
    a.result = {'model_calls': 0, 'curator_calls': 0, 'input_tokens': 0, 'output_tokens': 0,
                'model_wall_seconds': 0.0}
    a.gpu_known, a.invocation_steps = True, 0
    return a


FETCH = skill('fetch_object@v1', ['obj'], [], ['holding(obj)'],
              'act("go to table 1")\nact(f"take {obj} from table 1")',
              [{'snapshot': START, 'bindings': {'obj': 'apple 1'}}])
STORE = skill('store_object@v1', ['obj', 'place'], ['holding(obj)'], ['located(obj, place)'],
              'act(f"go to {place}")\nact(f"open {place}")\nact(f"move {obj} to {place}")',
              [{'snapshot': HOLDING, 'bindings': {'obj': 'apple 1', 'place': 'cabinet 1'}}])


class ConsolidationTests(unittest.TestCase):
    def test_cleanup_uses_evidence_not_length(self):
        short_used = skill('take_object@v1', ['obj'], [], ['holding(obj)'], 'act(f"take {obj} from table 1")')
        long_ignored = skill('fetch_object@v1', ['obj'], [], ['holding(obj)'], FETCH.body)
        failing = skill('store_object@v1', ['obj', 'place'], [], ['located(obj, place)'], STORE.body)
        stats = {'take_object@v1': {'offered': 10, 'chosen': 6, 'ok': 6, 'arguments': [{'obj': 'a 1'}, {'obj': 'b 1'}]},
                 'fetch_object@v1': {'offered': 12, 'chosen': 0, 'ok': 0, 'arguments': []},
                 'store_object@v1': {'offered': 9, 'chosen': 6, 'ok': 1, 'arguments': []}}
        lib = library(short_used, long_ignored, failing, meta={'stats': stats})
        report = consolidate(agent(lib))
        self.assertEqual(sorted(r[0] for r in report['retired']), ['fetch_object@v1', 'store_object@v1'])
        self.assertEqual(sorted(lib.active), ['take_object'])          # a one-step skill that earns its keep stays
        self.assertEqual(lib.skills['fetch_object@v1'].status, 'retired')   # kept for audit
        self.assertIn('ignored', lib.meta['retired']['fetch_object@v1'])
        # A never-chosen skill survives one interval, then goes.
        idle = skill('grab_object@v1', ['obj'], [], ['holding(obj)'], FETCH.body)
        lib = library(idle)
        consolidate(agent(lib))
        self.assertIn('grab_object', lib.active)
        consolidate(agent(lib))
        consolidate(agent(lib))
        self.assertNotIn('grab_object', lib.active)

    def test_too_specific_skill_is_sent_alone_to_be_generalized(self):
        specific = skill('take_apple_from_table@v1', [], [], ['holding(apple 1)'],
                         'act("go to table 1")\nact("take apple 1 from table 1")',
                         [{'snapshot': START, 'bindings': {}}])
        general = {'candidate': {'name': 'take_object_from_place', 'description': 'take any object from a place',
                                 'parameters': {'o': 'entity', 'p': 'entity'}, 'preconditions': [],
                                 'postconditions': ['holding(o)'],
                                 'body': 'act(f"go to {p}")\nact(f"take {o} from {p}")'},
                   'mappings': {'take_apple_from_table@v1': {'o': 'apple 1', 'p': 'table 1'}}}
        lib = library(specific)
        self.assertTrue(too_specific(lib, lib.skills['take_apple_from_table@v1']))
        report = consolidate(agent(lib, Curator(general)))
        self.assertEqual(report['merged'], [['take_object_from_place@v1', ['take_apple_from_table@v1']]])
        self.assertEqual(sorted(lib.active), ['take_object_from_place'])
        # Without a usable mapping the gate rejects it rather than guess.
        lib = library(specific)
        report = consolidate(agent(lib, Curator({**general, 'mappings': {'take_apple_from_table@v1': {}}})))
        self.assertEqual(report['merged'], [])
        self.assertEqual(sorted(lib.active), ['take_apple_from_table'])

    def test_repeated_pair_becomes_replay_tested_meta_skill(self):
        pairs = {'fetch_object@v1>store_object@v1': {'count': 3, 'example': {
            'snapshot': START, 'first': {'obj': 'apple 1'}, 'second': {'obj': 'apple 1', 'place': 'cabinet 1'}}}}
        lib = library(FETCH, STORE, meta={'pairs': pairs})
        report = consolidate(agent(lib))
        self.assertEqual(len(report['composed']), 1, report)
        meta = lib.skills[report['composed'][0][0]]
        self.assertEqual(meta.parameters, {'obj': 'entity', 'place': 'entity'})
        self.assertIn('call("fetch_object@v1"', meta.body)
        self.assertEqual(meta.postconditions, ['located(obj, place)'])
        self.assertEqual(meta.status, 'active')
        # Called skills are never retired while a meta-skill depends on them.
        lib.meta['uses_at_check'] = {s.id: 0 for s in lib.current()}
        consolidate(agent(lib))
        self.assertIn('fetch_object', lib.active)

    def test_merge_must_pass_every_member_replay(self):
        other = skill('grab_object@v1', ['thing'], [], ['holding(thing)'],
                      'act("go to table 1")\nact(f"take {thing} from table 1")',
                      [{'snapshot': START, 'bindings': {'thing': 'apple 1'}}])
        good = {'candidate': {'name': 'take_object', 'description': 'take an object from the table',
                              'parameters': {'o': 'entity'}, 'preconditions': [], 'postconditions': ['holding(o)'],
                              'body': 'act("go to table 1")\nact(f"take {o} from table 1")'},
                'mappings': {'fetch_object@v1': {'o': 'obj'}, 'grab_object@v1': {'o': 'thing'}}}
        cfg = Settings(merge_similarity=0.0)
        lib = library(FETCH, other)
        a = agent(lib, Curator(good))
        a.cfg = cfg
        report = consolidate(a)
        self.assertEqual(report['merged'], [['take_object@v1', ['fetch_object@v1', 'grab_object@v1']]])
        self.assertEqual(sorted(lib.active), ['take_object'])
        self.assertEqual(len(lib.skills['take_object@v1'].tests), 2)
        self.assertEqual(a.result['curator_calls'], 1)
        self.assertEqual(a.result['input_tokens'], 100)

        broken = {**good, 'candidate': {**good['candidate'], 'body': 'act("look")\nact("look")'}}
        lib = library(FETCH, other)
        a = agent(lib, Curator(broken))
        a.cfg = cfg
        report = consolidate(a)
        self.assertEqual(report['merged'], [])
        self.assertEqual(sorted(lib.active), ['fetch_object', 'grab_object'])   # members restored/untouched

    def test_lesson_needs_simulated_fix_and_is_scored_by_outcomes(self):
        from living_library.consolidation import lessons_for, record_episode
        failure = {'task': {**TASK, 'task_type': 'pick'}, 'goal': 'put apple in cabinet', 'actions': [], 'final': ''}
        good = {'lesson': 'Open a closed receptacle before trying to put something in it.', 'applies_to': 'pick'}
        lib = library(meta={'failures': [failure]})
        a = agent(lib, Curator(good))
        report = consolidate(a)
        self.assertEqual(report['lessons'], [good['lesson']], report)
        self.assertEqual(a.result['simulated_episodes'], 1)          # no won game of this kind yet
        # The now-winning simulated game wrote a skill, kept because the lesson was admitted.
        self.assertEqual(len(report['harvested']), 1)
        self.assertIn(report['harvested'][0].split('@')[0], lib.active)
        self.assertGreater(a.result['model_calls'], 1)               # simulation calls are charged
        self.assertEqual(lessons_for(lib, 'pick'), [good['lesson']])
        self.assertEqual(lessons_for(lib, 'heat'), [])
        # Outcomes while shown move the score; at -3 the lesson is dropped at the next consolidation.
        b = agent(lib)
        b.task, b.lessons_shown = {**TASK, 'task_type': 'pick'}, [good['lesson']]
        b.result.update(success=False, trace=[], goal='g')
        for _ in range(3):
            record_episode(b)
        self.assertEqual(lib.meta['lessons'][0]['score'], -3)
        report = consolidate(agent(lib, Curator({'lesson': 'x'})))
        self.assertEqual(lessons_for(lib, 'pick'), [])
        self.assertEqual(report['lessons_dropped'], [good['lesson']])

        named = {'lesson': 'The apple is always in drawer 3.', 'applies_to': 'pick'}
        lib = library(meta={'failures': [failure]})
        report = consolidate(agent(lib, Curator(named)))
        self.assertEqual(report['lessons'], [])
        self.assertIn('numbered object', report['rejected'][-1][2])

    def test_empty_meta_keeps_snapshots_identical(self):
        lib = library(FETCH)
        self.assertNotIn('meta', lib.snapshot())
        lib.meta['consolidations'] = 1
        self.assertEqual(Library.restore(lib.snapshot(), Settings()).meta, {'consolidations': 1})


if __name__ == '__main__':
    unittest.main()
