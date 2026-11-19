"""Large-library lab benchmark (results/lab/BRIEF.md). Run in WSL with the project venv.

  python tools/lab_bench.py snapshot            # real rules, queries, practice goals -> results/lab/data/real.json
  python tools/lab_bench.py variants            # model-written variants (cached)     -> results/lab/data/variants.json
  python tools/lab_bench.py run [--sizes ...] [--seeds 3] [--methods baseline random]
                                                # metrics per method x N             -> results/lab/data/bench.json
  python tools/lab_bench.py show N [--seed 0]   # print a synthetic library with its labels (spot checks)
"""
import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from living_library.lab import data, metrics, methods, synth  # noqa: E402

DATA = data.ROOT / 'results' / 'lab' / 'data'


def embedder():
    from living_library.config import Settings
    from living_library.library import SentenceEmbedding
    cfg = Settings.load(str(data.ROOT / 'configs' / 'pilot.json'))
    return SentenceEmbedding(cfg.embedding, cfg.embedding_revision)


def load():
    real = json.loads((DATA / 'real.json').read_text())
    variants = [v for p in sorted(DATA.glob('variants*.json')) for v in json.loads(p.read_text())]
    return real, synth.flatten(variants, real['rules'])


def library(real, cands, n, seed, sim, goals, junk_counts='same', other_kind_junk=False, junk_share=0.2):
    return synth.build(real['rules'], cands, n, seed, sim, goals, junk_counts, other_kind_junk, junk_share)


def cmd_run(a):
    real, cands = load()
    emb = embedder()
    goals = synth.goal_bank()
    queries = real['queries']
    results = []
    for seed in range(a.seeds):
        for n in a.sizes:
            share = None if a.junk_share < 0 else a.junk_share
            rules, meta, stats = library(real, cands, n, seed, emb.similarity, goals, a.junk_counts, a.other_kind_junk, share)
            by_id = {r['id']: r for r in rules}
            comp = Counter(m['cls'] for m in meta.values())
            for name in a.methods:
                fn = methods.METHODS[name]
                rows, split_rows, started = [], {'id': [], 'ood': []}, time.monotonic()
                for q in queries:
                    top = fn(rules, q, max(metrics.KS), emb.similarity)
                    rel = metrics.relevant_groups(rules, meta, q, synth.label)
                    row = metrics.score(top, by_id, meta, q, rel, synth.label)
                    row['relevant_groups'] = len(rel)
                    row['candidates'] = sum(r['task_type'] in (q['task_type'], 'all') for r in rules)
                    rows.append(row)
                    split_rows[q['split']].append(row)
                seconds = (time.monotonic() - started) / len(queries)
                res = {'method': name, 'n': n, 'seed': seed, 'size': stats['size'], 'composition': dict(comp),
                       'merge_gate_skipped': stats['merge_gate_skipped'], 'seconds_per_query': seconds,
                       'model_calls_per_query': 0, 'junk_counts': a.junk_counts, 'other_kind_junk': a.other_kind_junk,
                       'junk_share': share,
                       'relevant_groups': sum(r['relevant_groups'] for r in rows) / len(rows),
                       'candidates': sum(r['candidates'] for r in rows) / len(rows),
                       'library_junk': sum(m['junk'] for m in meta.values()) / len(meta),
                       'all': metrics.mean(rows), **{s: metrics.mean(v) for s, v in split_rows.items() if v}}
                results.append(res)
                m8 = res['all'][8]
                print(f"seed {seed} N={n:4d} ({stats['size']}) {name:9s} libjunk={res['library_junk']:.2f} cand={res['candidates']:.0f} rel={res['relevant_groups']:.1f} "
                      f"useful@8={m8['useful']:.2f} R@8={m8['recall']:.3f} P@8={m8['precision']:.3f} nDCG@8={m8['ndcg']:.3f} dup={m8['dup']:.3f} "
                      f"junk={m8['junk']:.3f} wrong={m8['wrong']:.3f} {seconds * 1000:.0f} ms/q", flush=True)
    out = Path(a.output)
    out.write_text(json.dumps(results, indent=1))
    print('wrote', out)


def cmd_show(a):
    real, cands = load()
    emb = embedder()
    rules, meta, stats = library(real, cands, a.n, a.seed, emb.similarity, synth.goal_bank())
    print(stats)
    for r in rules:
        m = meta[r['id']]
        print(f"{r['id']:9s} {m['cls']:16s} {'JUNK ' if m['junk'] else ''}{synth.short(r['task_type']):6s} "
              f"W{r['alpha'] - 1}/L{r['beta'] - 1} {r['type'][:12]:12s} {r['rule']}")


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest='cmd', required=True)
    sub.add_parser('snapshot')
    v = sub.add_parser('variants')
    v.add_argument('--round', type=int, default=0, help='0: variants.json; n > 0: variants-n.json (more variants)')
    r = sub.add_parser('run')
    r.add_argument('--sizes', type=int, nargs='+', default=[15, 50, 100, 200, 300, 500])
    r.add_argument('--seeds', type=int, default=3)
    r.add_argument('--junk-counts', choices=['same', 'worse'], default='same',
                   help='Beta counts of junk variants: as other rules (default) or flipped to mostly lost')
    r.add_argument('--methods', nargs='+', default=['baseline', 'random'])
    r.add_argument('--other-kind-junk', action='store_true', help='label every other-kind variant junk (sensitivity)')
    r.add_argument('--junk-share', type=float, default=0.2, help='junk share kept fixed across N (-1: as generated)')
    r.add_argument('--output', default=str(DATA / 'bench.json'))
    s = sub.add_parser('show')
    s.add_argument('n', type=int)
    s.add_argument('--seed', type=int, default=0)
    a = p.parse_args()
    if a.cmd == 'snapshot':
        d = data.snapshot()
        print(len(d['rules']), 'real visible rules,', len(d['queries']), 'queries')
    elif a.cmd == 'variants':
        from living_library.lab.client import CachedChat
        real = json.loads((DATA / 'real.json').read_text())
        chat = CachedChat(DATA / 'model-cache.sqlite')
        name = 'variants.json' if a.round == 0 else f'variants-{a.round}.json'
        out = synth.generate_variants(real['rules'], chat, DATA / name, a.round)
        print(len(out), 'rules varied;', chat.calls, 'model calls', f'{chat.seconds:.0f}s',
              len(synth.flatten(out, real['rules'])), 'candidates')
    elif a.cmd == 'run':
        cmd_run(a)
    else:
        cmd_show(a)


if __name__ == '__main__':
    main()
