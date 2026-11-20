"""The rule library redesign of 2026-11-20 (LIBRARY-SPEC.md): write gate with the trace check, Builder
operations per case, append-only E-minus, the per-rule judge's evidence, bad/refine/retire with the revision
cap, useless retirement, update_note conversion, retrieval, build with a fake agent, and replay."""
import copy
import json
import types
import unittest

from living_library import avoid, manual

HEAT = 'pick_heat_then_place_in_recep'
LOOK = 'look_at_obj_in_light'
GOAL = 'heat some egg and put it in countertop.'


def ids(start=0):
    n = [start]

    def next_id():
        n[0] += 1
        return f'rule_{n[0]}'
    return next_id


def step(action, valid=True, after='OK.'):
    return {'action': action, 'valid': valid, 'after': after if valid else 'Nothing happens.'}


def words(text):
    return set(text.lower().replace('.', ' ').replace(',', ' ').split())


class Embedder:
    """Word-overlap similarity (1.0 for equal text)."""
    def similarity(self, query, texts):
        q = words(query)
        return [1.0 if t == query else len(q & words(t)) / max(1, len(q | words(t))) for t in texts]


def evidence(followed=0, total=None, s=0, shown=None, pos=0, neg=0):
    e = manual.empty_evidence()
    e.update(shown=followed if shown is None else shown, followed=followed, sum=s, pos=pos, neg=neg)
    return e


def rule(rule_id, kind='Special Phenomenon', text=None, task_type=HEAT, **extra):
    r = manual.new_rule(rule_id, kind, text or f'When {rule_id} applies, open the fridge.', '', task_type)
    r.update(extra)
    return r


def verdicts(rules, followed=True, score=1):
    return {r['id']: {'followed': followed, 'usefulness': score if followed else 0, 'reason': 'r', 'rule': r['rule']}
            for r in rules}


CTX = {'task': GOAL, 'task_type': HEAT, 'steps': ['go to fridge 1', 'open fridge 1', 'take egg 1 from fridge 1']}


class WriteGateTests(unittest.TestCase):
    TRACE = [step('go to desk 1'), step('take lamp 1', False), step('use desklamp 1')]

    def test_instructed_commands_must_have_worked_in_the_won_trace(self):
        self.assertEqual(manual.trace_problems('When the light is needed, take the lamp.', self.TRACE), ['take lamp'])
        self.assertEqual(manual.trace_problems('When the light is needed, use the desklamp.', self.TRACE), [])
        self.assertEqual(manual.trace_problems('When something is dark, never take the lamp.', self.TRACE), [])
        self.assertEqual(manual.trace_problems('When the light is needed, open the safe.', self.TRACE), ['open safe'])

    def test_a_failing_rule_gets_one_repair_then_is_rejected(self):
        calls = []

        def ask(role, payload):
            calls.append(payload)
            return {'rule': 'When the light is needed, use the desklamp.'}
        rules, log = [], []
        manual.apply(rules, [{'op': 'write_rule', 'type': 'Special Phenomenon',
                              'rule': 'When the light is needed, take the lamp.'}],
                     'indirect success', False, ids(), log, LOOK, ask=ask, trace=self.TRACE)
        self.assertEqual([r['rule'] for r in rules], ['When the light is needed, use the desklamp.'])
        self.assertIn('take lamp', calls[-1]['problems'][0])
        rules, log = [], []
        manual.apply(rules, [{'op': 'write_rule', 'type': 'Special Phenomenon',
                              'rule': 'When the light is needed, take the lamp.'}],
                     'indirect success', False, ids(), log, LOOK, ask=lambda r, p: {'rule': 'When dark, take the lamp.'},
                     trace=self.TRACE)
        self.assertEqual(rules, [])
        self.assertIn('did not work in the won game', log[-1])

    def test_notes_are_not_trace_checked_and_near_duplicates_merge_without_a_text_change(self):
        rules, log = [], []
        manual.apply(rules, [{'op': 'write_rule', 'type': 'Unresolved Error', 'rule': 'When dark, take the lamp.'}],
                     'failure', False, ids(), log, LOOK, trace=self.TRACE)
        self.assertEqual(len(rules), 1)
        old = rule('rule_7', text='When the light is needed, use the desklamp now.', task_type=LOOK)
        rules = [old]
        applied = manual.apply(rules, [{'op': 'write_rule', 'type': 'Special Phenomenon',
                                        'rule': 'When the light is needed, use the desklamp.'}], 'direct success',
                               False, ids(7), log, LOOK, similarity=lambda q, ts: [0.9] * len(ts), goal=GOAL,
                               trace=self.TRACE)
        self.assertEqual(applied[0]['op'], 'merge_rule')
        self.assertEqual(old['rule'], 'When the light is needed, use the desklamp now.')
        self.assertEqual(old['sources'], [{'task': GOAL, 'task_type': LOOK}])


class BuilderOpTests(unittest.TestCase):
    def write(self, kind, n):
        return {'op': 'write_rule', 'type': kind, 'rule': f'When case {"abcd"[n]} applies, open the fridge.'}

    def test_op_limits_per_case(self):
        for case, allowed, limit in (('direct success', {'Success Process', 'Special Phenomenon'}, 2),
                                     ('indirect success', {'Success Process', 'Special Phenomenon', 'Corrected Error'}, 2),
                                     ('corrected failure', {'Corrected Error', 'Success Process', 'Special Phenomenon'}, 2),
                                     ('failure', {'Unresolved Error'}, 1)):
            self.assertEqual(set(manual.CASE_TYPES[case]), allowed)
            rules, log = [], []
            kind = sorted(allowed - {'Success Process'})[0]
            manual.apply(rules, [self.write(kind, n) for n in range(4)], case, False, ids(), log, HEAT)
            self.assertEqual(len(rules), limit, case)
            self.assertEqual(sum('at most' in e for e in log), 4 - limit)

    def test_visible_text_is_never_rewritten_by_the_builder(self):
        recipe = rule('rule_1', 'Success Process', 'When heating: go to the microwave, heat it, put it there.')
        log = []
        manual.apply([recipe], [{'op': 'update_rule', 'id': 'rule_1', 'rule': 'new'},
                                {'op': 'update_note', 'id': 'rule_1', 'rule': 'new'},
                                {'op': 'upvote_rule', 'id': 'rule_1'},
                                {'op': 'note', 'id': 'rule_1', 'validation': 'This game showed it is incomplete.'}],
                     'direct success', False, ids(1), log, HEAT)
        self.assertEqual(recipe['rule'], 'When heating: go to the microwave, heat it, put it there.')
        self.assertEqual(recipe['validation'], 'This game showed it is incomplete.')
        self.assertEqual(len(log), 3)

    def test_append_only_writes_only(self):
        note = rule('rule_1', 'Unresolved Error', 'When the egg was not found, the fridge was closed.')
        rules, log = [note], []
        applied = manual.apply(rules, [{'op': 'note', 'id': 'rule_1', 'validation': 'v'},
                                       {'op': 'update_note', 'id': 'rule_1', 'rule': 'When x, y failed.'},
                                       self.write('Special Phenomenon', 1)], 'direct success', True, ids(1), log, HEAT)
        self.assertEqual([o['op'] for o in applied], ['write_rule'])
        self.assertEqual((note['validation'], note['rule']), ('', 'When the egg was not found, the fridge was closed.'))
        self.assertEqual(sum('append-only' in e for e in log), 2)


class UpdateNoteTests(unittest.TestCase):
    RETRY = [step('go to fridge 1'), step('open fridge 1'), step('take egg 1 from fridge 1')]

    def setUp(self):
        self.note = rule('rule_1', 'Unresolved Error', 'When the egg was not found, the search failed.')
        self.op = {'op': 'update_note', 'id': 'rule_1', 'type': 'Corrected Error',
                   'rule': 'When the object is not in sight, open the fridge instead of searching shelves.'}

    def test_a_retry_win_that_followed_the_text_makes_a_visible_corrected_error(self):
        self.note['ev'] = evidence(3, s=3)
        log = []
        applied = manual.apply([self.note], [self.op], 'corrected failure', False, ids(1), log, HEAT,
                               trace=self.RETRY, retry_check=lambda r: True)
        self.assertEqual((self.note['type'], self.note['hidden']), ('Corrected Error', False))
        self.assertTrue(manual.shown_to_agent(self.note))
        self.assertEqual(self.note['ev'], manual.empty_evidence())
        self.assertEqual(applied[0]['type'], 'Corrected Error')
        replayed = manual.replay([rule('rule_1', 'Unresolved Error', 'When the egg was not found, the search failed.')],
                                 applied, [])
        self.assertEqual(replayed[0]['type'], 'Corrected Error')

    def test_no_conversion_without_the_judge_or_the_trace_check_or_outside_a_corrected_failure(self):
        for case, check, trace in (('corrected failure', lambda r: False, self.RETRY),
                                   ('corrected failure', lambda r: True, [step('go to fridge 1')]),
                                   ('failure', lambda r: True, self.RETRY)):
            note, log = copy.deepcopy(self.note), []
            manual.apply([note], [self.op], case, False, ids(1), log, HEAT, trace=trace, retry_check=check)
            self.assertEqual(note['type'], 'Unresolved Error', case)
            self.assertFalse(manual.shown_to_agent(note))
            self.assertEqual(note['rule'], self.op['rule'])                    # reworded, still hidden


class JudgeTests(unittest.TestCase):
    def agent(self, answer):
        calls = []

        def ask(role, payload):
            calls.append((role, payload))
            if isinstance(answer, Exception):
                raise answer
            return answer
        trace = [step('go to fridge 1', after='The fridge 1 is closed.'), step('dance', False),
                 step('open fridge 1', after='You open the fridge 1. You win!')]
        return types.SimpleNamespace(_ask=ask, result={'trace': trace, 'success': True}, public_task={'goal': GOAL},
                                     rules_shown=['rule_1', 'rule_2', 'rule_9']), calls

    def test_one_outcome_blind_call_per_shown_visible_rule(self):
        agent, calls = self.agent({'followed': 'yes', 'usefulness': '2', 'reason': 'it helped'})
        rules = [rule('rule_1'), rule('rule_2', 'Unresolved Error', 'When x, y failed.')]
        found = manual.judge_shown(agent, rules, [])
        self.assertEqual(list(found), ['rule_1'])                              # notes are never judged
        self.assertEqual(found['rule_1']['usefulness'], 2)
        role, payload = calls[0]
        self.assertEqual(role, 'judge')
        self.assertEqual(payload['rule'], {'type': 'Special Phenomenon', 'rule': rules[0]['rule']})
        self.assertEqual([s['action'] for s in payload['steps']], ['go to fridge 1', 'open fridge 1'])
        self.assertNotIn('observation', payload['steps'][-1])                  # the final observation reveals a win
        self.assertNotIn('You win', json.dumps(payload))
        self.assertNotIn('success', json.dumps(payload))

    def test_bad_answers_and_failures_give_no_evidence(self):
        for answer in ({'followed': 'maybe', 'usefulness': 1}, {'followed': 'yes', 'usefulness': 3},
                       {'followed': 'yes', 'usefulness': 'high'}, {'followed': 'yes'}, 'text',
                       RuntimeError('timeout')):
            agent, _ = self.agent(answer)
            errors = []
            self.assertEqual(manual.judge_shown(agent, [rule('rule_1')], errors), {}, answer)
            self.assertIn('no evidence', errors[0])
        self.assertEqual(manual.parse_verdict({'followed': False, 'usefulness': -2})['usefulness'], 0)

    def test_observe_counts_followed_and_shown_and_keeps_six_contexts_of_each_sign(self):
        r = rule('rule_1')
        for n in range(10):
            manual.observe([r], verdicts([r], score=1 if n % 2 else -1), CTX, n, n % 3 == 0)
        manual.observe([r], verdicts([r], followed=False), CTX, 10, True)
        manual.observe([r], {}, CTX, 11, True)                                  # judge failed: nothing
        self.assertEqual({k: r['ev'][k] for k in ('shown', 'followed', 'sum', 'pos', 'neg')},
                         {'shown': 11, 'followed': 10, 'sum': 0, 'pos': 5, 'neg': 5})
        self.assertEqual(r['ev']['won'] + r['ev']['lost'], 10)
        self.assertEqual(r['last_used'], 10)
        self.assertEqual((sum(c['score'] > 0 for c in r['contexts']), sum(c['score'] < 0 for c in r['contexts'])),
                         (5, 5))
        for n in range(4):
            manual.observe([r], verdicts([r], score=2), CTX, 20 + n, True)
        self.assertEqual(sum(c['score'] > 0 for c in r['contexts']), manual.K_CONTEXTS)
        self.assertEqual(manual.mean(r), 8 / (14 + manual.PRIOR))

    def test_a_verdict_on_an_old_text_is_not_counted(self):
        r = rule('rule_1')
        judged = verdicts([r])
        r['rule'] = 'When another text, open the fridge.'
        manual.observe([r], judged, CTX, 0, True)
        self.assertEqual(r['ev'], manual.empty_evidence())


class Refiner:
    def __init__(self, text='When the object is cold, open the fridge first.', fail=False):
        self.text, self.fail, self.calls = text, fail, []

    def __call__(self, role, payload):
        self.calls.append((role, payload))
        if self.fail:
            raise RuntimeError('server down')
        return {'rule': self.text}


class ManagementTests(unittest.TestCase):
    def bad_rule(self, rule_id='rule_1', revisions=0, kind='Special Phenomenon'):
        r = rule(rule_id, kind, revisions=revisions)
        for n in range(6):
            manual.observe([r], verdicts([r], score=-1), CTX, n, False)
        return r

    def test_bad_needs_six_followed_games_and_a_shrunk_mean_of_minus_a_half(self):
        r = rule('rule_1', ev=evidence(5, s=-5))
        self.assertFalse(manual.bad(r))                                          # 5 followed games
        r['ev'] = evidence(6, s=-3)
        self.assertFalse(manual.bad(r))                                          # m = -3/8
        r['ev'] = evidence(6, s=-4)
        self.assertTrue(manual.bad(r))                                           # m = -4/8
        self.assertFalse(manual.bad({**r, 'type': 'Unresolved Error', 'hidden': True}))

    def test_refine_one_per_game_lowest_mean_first_then_retire_at_the_cap(self):
        a, b = self.bad_rule('rule_1'), self.bad_rule('rule_2')
        b['ev']['sum'] -= 2
        capped = self.bad_rule('rule_3', revisions=manual.MAX_REVISIONS)
        pattern = self.bad_rule('rule_4', kind=avoid.TYPE)
        self.assertEqual(manual.decisions([a, b, capped, pattern]), (b, [capped, pattern]))
        rules, report = [a, b, capped], {'operations': [], 'errors': []}
        agent = types.SimpleNamespace(_ask=Refiner())
        manual.manage(agent, rules, report)
        self.assertEqual([r['id'] for r in rules], ['rule_1', 'rule_2'])
        self.assertEqual(b['rule'], 'When the object is cold, open the fridge first.')
        self.assertEqual((b['revisions'], b['ev'], b['contexts']), (1, manual.empty_evidence(), []))
        self.assertEqual(b['total']['followed'], 6)                             # lifetime kept
        self.assertEqual([o['op'] for o in report['operations']], ['retire', 'refine'])
        payload = agent._ask.calls[0][1]
        self.assertEqual(len(payload['misled_games']), 6)
        self.assertEqual(payload['misled_games'][0]['reason'], 'r')

    def test_refinement_failure_retires(self):
        for refiner in (Refiner(fail=True), Refiner(text='When the object is cold, open the safe first.'),
                        Refiner(text='When on floor 3, open the fridge.')):
            r = self.bad_rule()
            rules, report = [r], {'operations': [], 'errors': []}
            manual.manage(types.SimpleNamespace(_ask=refiner), rules, report)
            self.assertEqual(rules, [], refiner.text)
            self.assertEqual(report['operations'][0]['check'], 'bad')
            self.assertIn('refinement failed', report['operations'][0]['reason'])

    def test_useless_and_capacity_in_batch_upkeep(self):
        ignored = rule('rule_1', 'Success Process', 'When heating: go to the microwave, heat it, put it there.')
        ignored['ev'] = evidence(1, shown=10)
        kept = rule('rule_2', ev=evidence(2, shown=10))
        rules = [ignored, kept]
        ops = manual.batch_upkeep(rules, set(), None)
        self.assertEqual([(o['op'], o['id']) for o in ops], [('retire', 'rule_1')])
        self.assertIn('useless', ops[0]['reason'])
        self.assertEqual(manual.replay([copy.deepcopy(ignored), copy.deepcopy(kept)], ops, []), rules)

    def test_capacity_pruning_order(self):
        old_cap = manual.CAPACITY
        manual.CAPACITY = 3
        try:
            rules = [rule('rule_1', ev=evidence(4, s=4)), rule('rule_2', 'Unresolved Error', 'When x, y failed.'),
                     rule('rule_3', ev=evidence(4, s=-1)), rule('rule_4', ev=evidence(4, s=-1), last_used=9),
                     rule('rule_5', 'Unresolved Error', 'When a, b failed.')]
            ops = manual.prune(rules)
            self.assertEqual([o['id'] for o in ops], ['rule_2', 'rule_5'])
            manual.CAPACITY = 2
            self.assertEqual([o['id'] for o in manual.prune(rules)], ['rule_3'])     # lowest m, least recently used
        finally:
            manual.CAPACITY = old_cap


class RetrievalTests(unittest.TestCase):
    def test_usefulness_reorders_within_a_kind_and_relevance_is_task_keyed(self):
        a = rule('rule_1', text='When the fridge is closed, open it.')
        b = rule('rule_2', text='When the fridge is closed, open it first.')
        b['ev'] = evidence(6, s=9)
        sim = Embedder().similarity
        self.assertEqual([r['id'] for r in manual.for_agent([a, b], HEAT, 8, GOAL, sim)], ['rule_2', 'rule_1'])
        b['ev'] = evidence(6, s=-6)
        self.assertEqual([r['id'] for r in manual.for_agent([a, b], HEAT, 8, GOAL, sim)], ['rule_1', 'rule_2'])
        # h = lifetime helped games weights the task evidence (sources and helped contexts)
        c = rule('rule_3', text='When done, stop.', total=evidence(8, pos=8),
                 contexts=[{**CTX, 'score': 2, 'won': True}])
        rel, ev = manual.relevance(c, {c['rule']: 0.0, GOAL: 1.0})
        self.assertEqual(ev, 1.0)
        self.assertAlmostEqual(rel, 0.8)

    def test_one_slot_for_the_best_rarely_shown_rule(self):
        seen = [rule(f'rule_{i}', text=f'When step {i}, open the fridge.', ev=evidence(1, s=1, shown=5))
                for i in range(1, 10)]
        new = rule('rule_10', text='When nothing helps, look around.')
        shown = manual.for_agent(seen + [new], HEAT, manual.SHOWN, GOAL, Embedder().similarity)
        self.assertEqual(len(shown), manual.SHOWN)
        self.assertEqual(shown[-1]['id'], 'rule_10')
        self.assertFalse(any(r['hidden'] for r in shown))


# ----- build with a fake agent, and replay ------------------------------------------------------------------

class ScriptedModel:
    """Scripted answers per role; the judge's verdict is looked up by rule text (default followed, 0)."""
    def __init__(self, builder_ops=(), scores=None, refined='When the object is cold, open the fridge first.'):
        self.builder_ops, self.scores, self.refined, self.calls = list(builder_ops), scores or {}, refined, []

    def __call__(self, role, payload):
        self.calls.append(role)
        if role == 'judge':
            score = self.scores.get(payload['rule']['rule'], 0)
            if score is None:
                raise RuntimeError('judge failed')
            return {'followed': 'yes', 'usefulness': score, 'reason': 'scripted'}
        if role == 'builder':
            return {'diagnosis': 'imperfect rules', 'operations': copy.deepcopy(self.builder_ops)}
        if role == 'refiner':
            return {'rule': self.refined}
        if role == 'reflector':
            return {'reflection': 'Open the fridge first.'}
        return {'rule': None}


class FakeAgent:
    def __init__(self, condition, rules, model, shown, success=True, position=0, batch=1):
        self.cfg = types.SimpleNamespace(practice_batch=batch)
        self.condition, self.rules, self._ask = condition, rules, model
        self.rules_shown = shown
        self.embedder = Embedder()
        trace = [step('go to fridge 1'), step('open fridge 1'), step('take egg 1 from fridge 1'),
                 step('go to microwave 1'), step('heat egg 1 with microwave 1'), step('go to countertop 1'),
                 step('move egg 1 to countertop 1')]
        self.result = {'trace': trace if success else trace[:2] + [step('dance', False)], 'success': success,
                       'goal': GOAL, 'model_calls': 0, 'input_tokens': 0, 'output_tokens': 0,
                       'model_wall_seconds': 0.0}
        self.task, self.public_task = {'task_type': HEAT, 'id': f'task{position}'}, {'goal': GOAL}
        self.seed, self.context, self.plan_text = 1, {'position': position}, 'heat ; place'
        self.gpu, self.gpu_known = 0.0, True

    def retry_agent(self, reflections):
        outer = self

        class Replay:
            def run(self, task, seed, context):
                return {**outer.result, 'success': True, 'trace': FakeAgent('E', [], None, []).result['trace'],
                        'gpu_seconds': 0.0}
        return Replay()


def strip(rules):
    return json.loads(json.dumps(rules, sort_keys=True))


class BuildTests(unittest.TestCase):
    def library(self):
        recipe = rule('rule_1', 'Success Process', 'When heating: go to the microwave, heat it, put it there.')
        harmful = rule('rule_2', text='When the egg is hot, open the safe.')
        for n in range(5):
            manual.observe([harmful], verdicts([harmful], score=-1), CTX, n, False)
        return [recipe, harmful]

    def run_build(self, condition, rules, model, shown, **kw):
        agent = FakeAgent(condition, rules, model, shown, **kw)
        return manual.build(agent), agent

    def test_e_build_judges_writes_and_refines_and_replay_reproduces_it(self):
        start = self.library()
        rules = copy.deepcopy(start)
        model = ScriptedModel([{'op': 'write_rule', 'type': 'Special Phenomenon',
                                'rule': 'When the object is not in sight, open the fridge.'},
                               {'op': 'note', 'id': 'rule_2', 'validation': 'It sent the agent to the safe.'}],
                              scores={start[0]['rule']: 2, start[1]['rule']: -2})
        report, _ = self.run_build('E', rules, model, ['rule_1', 'rule_2'])
        self.assertEqual(report['judged'], {'rule_1': {'followed': True, 'usefulness': 2},
                                            'rule_2': {'followed': True, 'usefulness': -2}})
        self.assertEqual(model.calls.count('judge'), 2)
        by_id = {r['id']: r for r in rules}
        self.assertEqual(by_id['rule_2']['rule'], 'When the object is cold, open the fridge first.')   # refined
        self.assertEqual(by_id['rule_2']['revisions'], 1)
        self.assertEqual(by_id['rule_1']['ev']['sum'], 2)
        self.assertEqual(by_id['rule_3']['rule'], 'When the object is not in sight, open the fridge.')
        self.assertEqual(strip(manual.replay(copy.deepcopy(start), report['operations'], [], start)), strip(rules))

    def test_e_minus_records_evidence_but_never_changes_or_removes(self):
        start = self.library()
        start[1]['ev']['shown'] = 30                                            # bad and useless in E
        rules = copy.deepcopy(start)
        model = ScriptedModel([{'op': 'note', 'id': 'rule_2', 'validation': 'v'}],
                              scores={start[1]['rule']: -2})
        report, _ = self.run_build('E-minus', rules, model, ['rule_2'])
        self.assertEqual([r['rule'] for r in rules if r['type'] != avoid.POOL], [r['rule'] for r in start])
        self.assertEqual(rules[1]['ev']['followed'], 6)
        self.assertTrue(manual.bad(rules[1]) and manual.useless(rules[1]))
        self.assertNotIn('refiner', model.calls)
        self.assertEqual(strip(manual.replay(copy.deepcopy(start), report['operations'], [])), strip(rules))

    def test_judge_failure_gives_no_evidence_in_build(self):
        rules = self.library()
        model = ScriptedModel(scores={rules[0]['rule']: None})
        report, _ = self.run_build('E', rules, model, ['rule_1'])
        self.assertEqual(rules[0]['ev'], manual.empty_evidence())
        self.assertTrue(any(e.startswith('judge rule_1') for e in report['errors']))

    def test_a_lost_game_writes_only_a_hidden_note_and_a_retry_win_converts_one(self):
        rules = self.library()
        model = ScriptedModel([{'op': 'write_rule', 'type': 'Corrected Error',
                                'rule': 'When the object is not in sight, open the fridge instead of the safe.'}],
                              scores={'When the object is not in sight, open the fridge instead of the safe.': 2})
        report, agent = self.run_build('E', rules, model, [], success=False)
        self.assertEqual(report['case'], 'corrected failure')                    # the fake retry wins
        written = next(r for r in rules if r['type'] == 'Corrected Error')
        self.assertTrue(manual.shown_to_agent(written))
        note = rule('rule_9', 'Unresolved Error', 'When the egg was not found, the safe was searched.')
        rules = self.library() + [note]
        text = 'When the object is not in sight, open the fridge instead of searching the safe.'
        model = ScriptedModel([{'op': 'update_note', 'id': 'rule_9', 'type': 'Corrected Error', 'rule': text}],
                              scores={text: 1})
        report, _ = self.run_build('E', rules, model, [], success=False)
        self.assertEqual((note['type'], note['rule']), ('Corrected Error', text))
        self.assertEqual(note['ev'], manual.empty_evidence())

    def test_batch_size_one_runs_the_upkeep_in_build(self):
        rules = self.library()
        rules[0]['ev'] = evidence(1, shown=12)
        report, _ = self.run_build('E', rules, ScriptedModel(), [])
        self.assertNotIn('rule_1', [r['id'] for r in rules])
        self.assertTrue(any(o['op'] == 'retire' and 'useless' in o['reason'] for o in report['operations']))
        rules = self.library()
        rules[0]['ev'] = evidence(1, shown=12)
        self.run_build('E', rules, ScriptedModel(), [], batch=8)                  # experiment.py runs it per batch
        self.assertIn('rule_1', [r['id'] for r in rules])


class ReplayTests(unittest.TestCase):
    def test_a_refine_is_dropped_when_the_rule_is_no_longer_bad_on_the_live_rules(self):
        base = BuildTests().library()
        mates = [copy.deepcopy(base), copy.deepcopy(base)]
        harmful = base[1]['rule']
        reports = []
        # game 0 (position 0): the judge finds the rule helpful; game 1: harmful (m = -6/8), so it refines it in-game
        for n, (rules, score) in enumerate(zip(mates, (2, -1))):
            agent = FakeAgent('E', rules, ScriptedModel(scores={harmful: score}), ['rule_2'], position=n, batch=8)
            reports.append(manual.build(agent))
        self.assertEqual(mates[1][1]['revisions'], 1)                            # refined on its private copy
        live, log = copy.deepcopy(base), []
        for report in reports:
            live = manual.replay(live, report['operations'], log, base)
        self.assertEqual(live[1]['rule'], harmful)                               # m = (-5+2-1)/(7+2) > -0.5
        self.assertEqual(live[1]['ev']['followed'], 7)
        self.assertTrue(any(entry[0].startswith('dropped (no longer bad') for entry in log))

    def test_one_text_change_per_rule_per_batch(self):
        base = BuildTests().library()
        live, log = copy.deepcopy(base), []
        for _ in range(6):
            manual.observe(live, verdicts([live[1]], score=-2), CTX, 0, False)
        ops = [{'op': 'refine', 'id': 'rule_2', 'rule': 'When A, open the fridge.', 'revision': 1}]
        live = manual.replay(live, ops, log, base)
        for _ in range(6):
            manual.observe(live, verdicts([live[1]], score=-2), CTX, 0, False)
        self.assertTrue(manual.bad(live[1]))
        live = manual.replay(live, [{**ops[0], 'rule': 'When B, open the fridge.'}], log, base)
        self.assertEqual(live[1]['rule'], 'When A, open the fridge.')
        self.assertEqual(log[-1][0], 'text change dropped (already changed in this batch)')

    def test_batch_upkeep_ops_replay_onto_the_same_library(self):
        base = BuildTests().library()
        live = copy.deepcopy(base)
        live.append(rule('rule_3', text='When the egg is hot, open the safe now.'))      # a batch-mate's twin
        live[0]['ev'] = evidence(0, shown=10)
        before = copy.deepcopy(live)
        ops = manual.batch_upkeep(live, {'rule_1', 'rule_2'}, lambda q, ts: [0.9] * len(ts))
        self.assertEqual([o['op'] for o in ops], ['retire', 'dedupe'])
        self.assertEqual(strip(manual.replay(before, ops, [])), strip(live))


if __name__ == '__main__':
    unittest.main()
