"""Short live practice run for one condition, then a readable report of how its rule manual evolved.

Plays the first N pilot practice games (same order and settings as the pilot) in a scratch folder,
writes the final rules to <output>/rules.json (MACLA "contexts", the refiner's per-game evidence, are
bookkeeping and are reduced to won/lost counts there; rules-full.json keeps them), and prints: what the Builder wrote, updated, voted,
merged, refined, retired and pruned per game, each failed game's retries and reflections, the
contrastive rules written from retry successes, the final manual with each rule's reliability and whether
the agent can see it (VISIBLE, or HIDDEN: Builder note / unconfirmed guess from a lost game), the ANTI-PATTERN
rules (avoid rules written from pooled never-won attempts, avoid.py) with the evidence behind each and what
happened to them (retired, contradicted, violated), the failure pool of each kind of task, and errors.

usage: python tools/mini_practice.py --games 48 --output /root/ll-runs/mini-macla [--condition E] [--workers 16]
"""
import argparse
import collections
import json
import re
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from living_library.config import Settings  # noqa: E402
from living_library.experiment import Runner, load_json, ordered, stream_spec  # noqa: E402
from living_library import avoid  # noqa: E402
from living_library.manual import HIDDEN, NUMBERED, shown_to_agent  # noqa: E402

# ALFWorld object kinds (portable things a task names). A rule naming one is about a task instance,
# not a general rule; tools and furniture (fridge, sinkbasin, drawer, ...) are allowed in general rules.
OBJECTS = set("""alarmclock apple baseballbat basketball book bowl box bread butterknife candle cd cellphone
    cloth creditcard cup dishsponge egg fork glassbottle kettle keychain knife ladle laptop lettuce mug
    newspaper pan papertowelroll pen pencil peppershaker pillow plate plunger pot potato remotecontrol
    saltshaker soapbar soapbottle spatula spoon spraybottle statue teddybear tissuebox toiletpaper tomato
    towel vase watch winebottle""".split())


def instance_specific(text):
    """Names a numbered object ("drawer 3") or a specific kind of object ("alarmclocks")."""
    words = {w.rstrip('s') for w in re.findall(r'[a-z]+', text.lower())} | set(re.findall(r'[a-z]+', text.lower()))
    return bool(NUMBERED.search(text)) or bool(words & OBJECTS)


def visibility(rule):
    """Whether the agent can be shown this rule, and if not, why."""
    if shown_to_agent(rule):
        return 'VISIBLE'
    return 'HIDDEN (Builder note)' if rule['type'] in HIDDEN else 'HIDDEN (unconfirmed guess from a lost game)'


def describe(rules):
    """Size, types, mean length and share of instance-specific rules of a manual."""
    rules = [r for r in rules if r['type'] != avoid.POOL]
    words = [len(r['rule'].split()) for r in rules]
    return {'rules': len(rules), 'types': dict(collections.Counter(r['type'] for r in rules)),
            'mean_words': round(statistics.mean(words), 1) if words else 0,
            'max_words': max(words, default=0),
            'visible': sum(shown_to_agent(r) for r in rules),
            'instance_specific': round(sum(instance_specific(r['rule']) for r in rules) / len(rules), 2) if rules else 0}


def trimmed(rule):
    """A rule without its refinement evidence (contexts are bookkeeping, not part of the rule)."""
    if rule['type'] == avoid.POOL:
        pool = rule['pool']
        return {'id': rule['id'], 'type': rule['type'], 'task_type': rule['task_type'],
                'pool': {'never_won_games': len(pool['games']), 'won_attempts': len(pool['won']),
                         'accepted_command_forms': len(pool['accepted']), 'retired_patterns': pool['retired'],
                         'declined_patterns': pool['declined']}}
    out = {k: v for k, v in rule.items() if k != 'contexts'}
    out['evidence'] = {'won': sum(c['won'] for c in rule.get('contexts', [])),
                       'lost': sum(not c['won'] for c in rule.get('contexts', []))}
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--games', type=int, default=48)
    p.add_argument('--output', required=True)
    p.add_argument('--condition', default='E')
    p.add_argument('--workers', type=int, default=16)
    a = p.parse_args()
    cfg = Settings.load('configs/pilot.json')
    manifest = load_json('/root/ll-runs/manifest.json')
    runner = Runner(cfg, manifest, a.output)
    tasks = ordered(manifest['splits']['practice'], cfg.practice_seed, a.games, repeat=True)
    spec = stream_spec(a.condition, 'practice', cfg.practice_seed, tasks)
    runner.execute([spec], workers=a.workers, log=print)
    n = runner.count(spec['key'])
    records = [load_json(runner._checkpoint(spec['key'], i))['record'] for i in range(n)]
    rules = load_json(runner._checkpoint(spec['key'], n - 1))['memory'].get('rules', []) if n else []
    Path(a.output, 'rules-full.json').write_text(json.dumps(rules, indent=1))
    Path(a.output, 'rules.json').write_text(json.dumps([trimmed(r) for r in rules], indent=1))

    print(f'\n{n} games, won {sum(r["success"] for r in records)} (first attempts)')
    totals = collections.Counter()
    contrastive = []
    for r in records:
        m = r.get('manual', {})
        ops = collections.Counter(op['op'] for op in m.get('operations', []))
        totals.update(ops)
        merged = sum('merged a new rule' in e for e in m.get('errors', []))
        totals['merged'] += merged
        retired = [e for e in m.get('errors', []) if e.startswith('retired ') or any(
            note in e for note in ('hidden Builder note', 'confirmed by a won game', 'keeps its text',
                                   'anti-pattern'))]
        totals['hidden guesses'] += sum('hidden Builder note' in e for e in retired)
        totals['confirmed guesses'] += sum('confirmed by a won game' in e for e in retired)
        errors = [e for e in m.get('errors', []) if 'merged a new rule' not in e and e not in retired]
        totals['rejected or failed'] += len(errors)
        retry = r.get('retries')
        if retry:
            totals['retried games'] += 1
            totals['retries'] += len(retry['attempts'])
            totals['retry successes'] += bool(retry['won'])
            totals['retry calls'] += retry['model_calls']
            totals['retry tokens'] += retry['input_tokens'] + retry['output_tokens']
        tries = (f" retries={len(retry['attempts'])}{' WON' if retry['won'] else ' lost'}" if retry else '')
        print(f"#{r['position']:3} {'WIN ' if r['success'] else 'fail'} {m.get('case', '-'):17} shown={len(r.get('rules_shown', []))} "
              f"ops={dict(ops)} merged={merged}{tries} rejected={errors[:2]}")
        for attempt in (retry or {}).get('attempts', []):
            print(f"       reflection {attempt['attempt']}: {attempt['reflection'][:150]}")
        for line in retired:
            print(f'       {line}')
        for op in m.get('operations', []):
            if op['op'] == 'pool_game':
                print(f"       pooled never-won game of {op['task_type']} ({len(op['game']['attempts'])} attempts)")
            if op['op'] in ('write_rule', 'refine') or (op['op'] == 'update_rule' and op.get('type')):
                print(f"       {op['op']}: {op.get('type', '')} {op['rule'][:150]}")
                if m.get('case') == 'corrected failure' and op.get('type') == 'Corrected Error':
                    contrastive.append(op['rule'])
    print('\ntotals:', dict(totals))
    print(f'\nCONTRASTIVE RULES from retry successes ({len(contrastive)}):')
    for text in contrastive:
        print(f'  - {text}')
    anti = [r for r in rules if r['type'] == avoid.TYPE]
    print(f'\nANTI-PATTERNS written and kept ({len(anti)}); retired or contradicted: '
          f"{sum('anti-pattern' in e and ('retired' in e or 'contradicted' in e) for r in records for e in r.get('manual', {}).get('errors', []))}")
    for rule in anti:
        pat = rule['pattern']
        print(f"  {rule['id']} [{rule.get('task_type')}] {pat['kind']} {pat['sig'][1:]}: seen in {pat['games']} of "
              f"{pat['of_games']} lost tasks, {pat['attempts']} of {pat['of_attempts']} lost attempts, "
              f"{pat['wins_checked']} won attempts checked; violated {rule.get('violations', 0)}x, "
              f"Beta({rule.get('alpha', 1)},{rule.get('beta', 1)})\n      {rule['rule']}")
    for rule in rules:
        if rule['type'] == avoid.POOL:
            pool = rule['pool']
            print(f"  pool {rule.get('task_type')}: {len(pool['games'])} never-won games, {len(pool['won'])} won attempts, "
                  f"{len(pool['retired'])} retired patterns, declined {pool['declined']}")
    print(f'\nFINAL MANUAL ({len([r for r in rules if r["type"] != avoid.POOL])} rules): {describe(rules)}')
    for rule in sorted([r for r in rules if r['type'] != avoid.POOL], key=lambda x: (x['type'], -x.get('alpha', 1) / (x.get('alpha', 1) + x.get('beta', 1)))):
        a_, b_ = rule.get('alpha', 1), rule.get('beta', 1)
        print(f"{rule['id']:8} [{rule['type']}] {rule.get('task_type')} importance={rule.get('importance')} "
              f"Beta({a_},{b_}) mean={a_ / (a_ + b_):.2f} base={rule.get('base')} words={len(rule['rule'].split())}"
              f" {visibility(rule)}\n    {rule['rule'][:300]}")


if __name__ == '__main__':
    main()
