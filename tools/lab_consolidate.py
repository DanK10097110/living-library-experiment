"""Consolidation of underused rules (living_library/lab/consolidate.py). Run in WSL with the project venv.

  python tools/lab_consolidate.py plan  INPUT...   # who is underused / well-used, clusters, fold targets (no model)
  python tools/lab_consolidate.py build INPUT...   # C0 / A / B rules-full.json + merges + retrieval metrics
INPUT: a rules-full.json (results/lab/data/union-rules-full.json, results/practice-d/rules-full.json)."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from living_library import manual  # noqa: E402
from living_library.lab import consolidate as C, data, metrics, methods, synth  # noqa: E402
from lab_bench import DATA, embedder  # noqa: E402

OUT = data.ROOT / 'results' / 'lab' / 'consolidate'


def name_of(path):
    p = Path(path)
    return p.parent.name if p.name == 'rules-full.json' else p.name.replace('-rules-full.json', '')


def hand_junk(rule):
    return any(rule['rule'].startswith(j) for j in synth.HAND_JUNK)


def label_for(rule, info, query):
    """Merged rule: relevant if any source is (union of the sources' relevance); junk/wrong if all sources are."""
    if 'srcs' not in info:
        return synth.label(rule, info, query)
    res = [synth.label(s, i, query) for s, i in info['srcs']]
    return max(r[0] for r in res), all(r[1] for r in res), all(r[2] for r in res)


def strict_label_for(rule, info, query):
    """Merged rule judged by its own new text only (objects/actions of the text, junk if all sources are junk)."""
    if 'srcs' not in info:
        return synth.label(rule, info, query)
    own = dict(info, objects=sorted(synth.objects_in(rule['rule'])), junk=all(i['junk'] for _, i in info['srcs']))
    return synth.label(rule, own, query)


def metas(original, new, merges):
    by_id = {r['id']: r for r in original}
    base = {r['id']: {'cls': 'real', 'group': f"o{r['id']}", 'junk': hand_junk(r),
                      'objects': sorted(synth.objects_in(r['rule']))} for r in original}
    out = {}
    for r in new:
        out[r['id']] = base[r['id']]
    for m in merges:
        out[m['kept_id']] = dict(base[m['kept_id']], group=f"m{m['kept_id']}",
                                 srcs=[(by_id[i], base[i]) for i in m['sources']])
    return out


def bench(rules, meta, queries, sim, label):
    vis = [r for r in rules if C.visible(r)]
    by_id = {r['id']: r for r in vis}
    rows = []
    for q in queries:
        top = methods.baseline(rules, q, max(metrics.KS), sim)
        rel = metrics.relevant_groups(vis, meta, q, label)
        rows.append(metrics.score(top, by_id, meta, q, rel, label))
    m = metrics.mean(rows)
    return {k: {x: round(v, 4) for x, v in m[k].items()} for k in m}


def cmd_plan(a):
    sim = embedder().similarity
    for path in a.inputs:
        rules = json.loads(Path(path).read_text())
        under, well, info = C.select(rules)
        by_id = {r['id']: r for r in rules}
        print(f"== {name_of(path)}: {len(rules)} rules, pool {info['pool']}, p40 shown {info['shown_p40']:.2f}, "
              f"median {info['shown_median']:.2f}; underused {len(under)}, well-used {len(well)}")
        for rid in under:
            r = by_id[rid]
            print(f"  U {rid:8s} {synth.short(r['task_type']):6s} W{r['alpha'] - 1}/L{r['beta'] - 1} {r['rule'][:100]}")
        for (task, kind), group in C.by_scope(rules, set(under)).items():
            for cl in C.clusters(group, sim):
                if len(cl) > 1:
                    print('  cluster', synth.short(task), kind, [r['id'] for r in cl])
        s = sorted(((float(sim(by_id[u]['rule'], [by_id[w]['rule']])[0]), u, w) for u in under for w in well
                    if by_id[w]['type'] == by_id[u]['type'] and by_id[w]['task_type'] == by_id[u]['task_type']),
                   reverse=True)
        print('  fold candidates (sim, underused, well-used):', [(round(x, 2), u, w) for x, u, w in s[:12]])


def cmd_build(a):
    from living_library.lab.client import CachedChat
    emb = embedder()
    chat = CachedChat(DATA / 'model-cache.sqlite')
    real = json.loads((DATA / 'real.json').read_text())
    queries = real['queries']
    OUT.mkdir(parents=True, exist_ok=True)
    for path in a.inputs:
        name = name_of(path)
        original = json.loads(Path(path).read_text())
        built = {'C0': (original, [], [], {})}
        built['A'] = C.variant_a(original, chat, emb.similarity)
        built['B'] = C.variant_b(original, chat, emb.similarity)
        summary = {}
        for var, (rules, merges, rejected, info) in built.items():
            C.dump(rules, OUT / f'{name}-{var}-rules-full.json')
            meta = metas(original, rules, merges)
            vis = [r for r in rules if C.visible(r)]
            summary[var] = {
                'rules': len(rules), 'visible': len(vis), 'merges': len(merges),
                'rules_absorbed': sum(len(m['sources']) - 1 for m in merges), 'rejected': len(rejected),
                'info': {k: v for k, v in info.items() if k != 'base_rates'},
                'union': bench(rules, {k: v for k, v in meta.items()}, queries, emb.similarity, label_for),
                'strict': bench(rules, meta, queries, emb.similarity, strict_label_for),
                'merge_list': merges, 'rejected_list': rejected}
            print(name, var, {k: v for k, v in summary[var].items() if k not in ('merge_list', 'rejected_list', 'union', 'strict', 'info')},
                  'P@8', summary[var]['union'][8]['precision'], 'nDCG@8', summary[var]['union'][8]['ndcg'],
                  'strictP@8', summary[var]['strict'][8]['precision'], flush=True)
        (OUT / f'{name}-summary.json').write_text(json.dumps(summary, indent=1))
    print('model calls', chat.calls, f'{chat.seconds:.0f}s')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('cmd', choices=['plan', 'build'])
    p.add_argument('inputs', nargs='+')
    a = p.parse_args()
    {'plan': cmd_plan, 'build': cmd_build}[a.cmd](a)


if __name__ == '__main__':
    main()
