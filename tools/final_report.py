"""One combined, self-contained HTML report for a finished study (interactive charts + tables).
usage: python tools/final_report.py /root/ll-runs/study2 --curve /root/ll-runs/snap-curve-100 /root/ll-runs/snap-curve-200
       --output results/final-report/STUDY-REPORT.html
Sections: headline evaluation, learning curve on identical games (library after 100/150/200/300 practice games),
library growth and composition, practice success over time, success by task type, the six recipes' evidence,
replicate agreement, cost.
"""
import argparse
import collections
import glob
import json
import math
import os
from pathlib import Path

KINDS = [('pick_two_obj', 'two objects'), ('look_at_obj', 'look (lamp)'), ('pick_heat', 'heat'),
         ('pick_cool', 'cool'), ('pick_clean', 'clean'), ('pick_and_place', 'pick & place')]
LIB_STREAMS = ['E-0', 'E-1', 'E-minus-0', 'E-minus-1']
EVAL_STREAMS = [('C', 'C-11'), ('D', 'D-r0-11'), ('E r0', 'E-r0-11'), ('E r1', 'E-r1-11'),
                ('E-minus r0', 'E-minus-r0-11'), ('E-minus r1', 'E-minus-r1-11')]


def kind(task_type):
    for k, name in KINDS:
        if task_type.startswith(k):
            return name
    return task_type


def load(path):
    with open(path) as f:
        return json.load(f)


def records(base, key):
    out = []
    for f in sorted(glob.glob(f'{base}/checkpoints/{key}/0*.json')):
        out.append(load(f)['record'])
    return out


def wilson(k, n, z=1.96):
    if not n:
        return 0, 0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return round(100 * (c - h), 1), round(100 * (c + h), 1)


def rules_of(memory):
    r = memory.get('rules') or {}
    return list(r.values()) if isinstance(r, dict) else list(r)


def build(study, curves):
    study = Path(study)
    plan = {s['key']: s for s in load(study / 'plan.json')}
    task_kind = {}
    for s in plan.values():
        for t in s['tasks']:
            task_kind[t['id']] = kind(t['task_type'])
    data = {}

    # 1. headline evaluation
    head = []
    by_id = {}
    for label, suffix in EVAL_STREAMS:
        row = {'label': label}
        for split, prefix in (('ood', 'evaluation'), ('id', 'id-evaluation')):
            recs = records(study, f'{prefix}-{suffix}')
            k = sum(bool(r['success']) for r in recs)
            row[split] = {'k': k, 'n': len(recs), 'pct': round(100 * k / len(recs), 1), 'ci': wilson(k, len(recs))}
            by_id[(label, split)] = {r['task_id']: bool(r['success']) for r in recs}
            row.setdefault('tokens', []).extend((r.get('input_tokens') or 0) + (r.get('output_tokens') or 0)
                                                for r in recs)
            row.setdefault('gpu', []).extend(r.get('gpu_seconds') or 0 for r in recs)
        row['tokens'] = round(sum(row['tokens']) / len(row['tokens']))
        row['gpu'] = round(sum(row['gpu']) / len(row['gpu']), 1)
        head.append(row)
    data['headline'] = head

    # 2. learning curve on the snapshot games (identical games at every point)
    snap_keys = [k for k in plan if k.startswith('snapshot-')]
    at0 = sorted({int(k.split('-')[1]) for k in snap_keys})
    games = {}  # (cond, rep) -> {split: [task ids]}
    for k in snap_keys:
        s = plan[k]
        games.setdefault((s['condition'], s['replicate']), {})[k.split('-')[2]] = [t['id'] for t in s['tasks']]
    points = {}
    sources = [(a, study) for a in at0] + [(int(Path(c).name.rsplit('-', 1)[1]), Path(c)) for c in curves]
    for at, base in sources:
        for (cond, rep), splits in games.items():
            ok = n = 0
            for split in splits:
                recs = records(base, f'snapshot-{at}-{split}-{cond}-r{rep}-11')
                ok += sum(bool(r['success']) for r in recs)
                n += len(recs)
            if n:
                points.setdefault(f'{cond} r{rep}', {})[at] = round(100 * ok / n, 1)
    any_games = next(iter(games.values()))
    for (cond, rep) in games:
        label = f'{cond} r{rep}'
        ok = n = 0
        for split, ids in games[(cond, rep)].items():
            m = by_id[(label, split)]
            ok += sum(m[i] for i in ids)
            n += len(ids)
        points[label][300] = round(100 * ok / n, 1)
    for label in ('C', 'D'):
        ok = n = 0
        for split, ids in any_games.items():
            m = by_id[(label, split)]
            ok += sum(m[i] for i in ids)
            n += len(ids)
        points[label] = {'ref': round(100 * ok / n, 1)}
    data['curve'] = {'points': points, 'games': sum(len(v) for v in any_games.values()),
                     'at': sorted({a for p in points.values() for a in p if a != 'ref'})}

    # 3. library growth and composition; 4. practice success over time
    growth, comp, practice, recipes = {}, {}, {}, {}
    for st in LIB_STREAMS + ['D-0']:
        files = sorted(glob.glob(f'{study}/checkpoints/practice-{st}/0*.json'))
        wins = []
        for i, f in enumerate(files):
            d = load(f)
            wins.append(bool(d['record']['success']))
            if st != 'D-0' and (i % 5 == 4 or i == len(files) - 1):
                rs = rules_of(d['memory'])
                growth.setdefault(st, []).append({'game': i + 1, 'rules': len(rs),
                                                  'visible': sum(1 for r in rs if not r.get('hidden'))})
            if st != 'D-0' and i == len(files) - 1:
                comp[st] = dict(collections.Counter(r.get('type') or '?' for r in rs))
                recipes[st] = [{'id': r.get('id'), 'kind': kind(r.get('task_type') or ''), 'text': r.get('rule'),
                                'pos': (r.get('ev') or {}).get('pos', 0), 'neg': (r.get('ev') or {}).get('neg', 0),
                                'shown': (r.get('ev') or {}).get('shown', 0)}
                               for r in rs if r.get('type') == 'Success Process' and not r.get('hidden')]
        practice[st] = [round(100 * sum(wins[max(0, i - 49):i + 1]) / len(wins[max(0, i - 49):i + 1]), 1)
                        for i in range(49, len(wins))]
        practice[st + ':total'] = sum(wins)
    data.update(growth=growth, composition=comp, practice=practice, recipes=recipes)

    # 5. OOD success by task type
    kinds = {}
    for label, _ in EVAL_STREAMS:
        for split in ('ood',):
            for tid, ok in by_id[(label, split)].items():
                c = kinds.setdefault(task_kind[tid], {}).setdefault(label, [0, 0])
                c[0] += ok
                c[1] += 1
    data['kinds'] = {k: {lab: round(100 * a / b, 1) for lab, (a, b) in v.items()} for k, v in kinds.items()}
    data['kind_n'] = {k: next(iter(v.values()))[1] for k, v in kinds.items()}

    # 6. replicate agreement on practice games
    def pwins(st):
        return [bool(load(f)['record']['success']) for f in sorted(glob.glob(f'{study}/checkpoints/practice-{st}/0*.json'))]
    w = {st: pwins(st) for st in LIB_STREAMS}
    agree = {}
    for a, b in (('E-0', 'E-1'), ('E-minus-0', 'E-minus-1'), ('E-0', 'E-minus-0'), ('E-1', 'E-minus-1')):
        n = min(len(w[a]), len(w[b]))
        agree[f'{a} vs {b}'] = {'disagree': sum(w[a][i] != w[b][i] for i in range(n)), 'n': n}
    data['agreement'] = agree
    return data


PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Living Library Study</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
:root{--surface:#fcfcfb;--card:#ffffff;--text:#0b0b0b;--text2:#52514e;--muted:#8a8984;--grid:#e6e5e1;
--c:#8a8984;--d:#1baf7a;--e:#2a78d6;--em:#eb6834;}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--surface:#1a1a19;--card:#232322;--text:#f0efec;--text2:#c3c2b7;--muted:#8f8e88;--grid:#3a3a38;--c:#8f8e88;--d:#199e70;--e:#3987e5;--em:#d95926;}}
:root[data-theme="dark"]{--surface:#1a1a19;--card:#232322;--text:#f0efec;--text2:#c3c2b7;--muted:#8f8e88;--grid:#3a3a38;--c:#8f8e88;--d:#199e70;--e:#3987e5;--em:#d95926;}
body{margin:0;background:var(--surface);color:var(--text);font:15px/1.55 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:1060px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:26px;margin:8px 0 4px}h2{font-size:19px;margin:36px 0 6px}p,li{color:var(--text2)}
.card{background:var(--card);border:1px solid var(--grid);border-radius:10px;padding:16px;margin:12px 0}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
.tile{background:var(--card);border:1px solid var(--grid);border-radius:10px;padding:12px}
.tile b{display:block;font-size:26px;color:var(--text)}.tile span{color:var(--text2);font-size:13px}
.chart{position:relative;height:340px}.grid2{display:grid;grid-template-columns:1fr 1fr;gap:12px}
@media(max-width:760px){.grid2{grid-template-columns:1fr}.chart{height:280px}}
table{border-collapse:collapse;width:100%;font-size:13.5px}th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--grid)}
th{color:var(--text2);font-weight:600}td.num{text-align:right;font-variant-numeric:tabular-nums}
details summary{cursor:pointer;color:var(--text2);font-size:13px;margin-top:6px}.scroll{overflow-x:auto}
.sw{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px;vertical-align:middle}
</style></head><body><main>
<h1>Living Library Study</h1>
<p>ALFWorld with Qwen3.5-9B: 3,104 episodes. Conditions: <b>C</b> (no memory), <b>D</b> (its own past trajectories), <b>E</b> (managed rule library), <b>E-minus</b> (same rule writer, no management). E and E-minus each ran two practice replicates of 300 games. Evaluation: 134 games in unseen rooms (OOD, primary) and 70 games in seen rooms (ID), with the library frozen.</p>
<div class="tiles" id="tiles"></div>

<h2>1. Final evaluation</h2>
<p>First-attempt success with 95% Wilson intervals. E and E-minus are tied on average; both are clearly above D and C.</p>
<div class="grid2"><div class="card"><div class="chart"><canvas id="ood"></canvas></div></div>
<div class="card"><div class="chart"><canvas id="id"></canvas></div></div></div>
<details><summary>Table</summary><div class="scroll" id="headtab"></div></details>

<h2>2. Learning curve: library after 1/3, 1/2, 2/3 and all of practice</h2>
<p>Each library frozen after 100, 150, 200 and 300 practice games, played on <b>the same <span id="ng"></span> games</b> (40 OOD + 40 ID from the evaluation sets). C and D are shown as flat references on the same games.</p>
<div class="card"><div class="chart"><canvas id="curve"></canvas></div></div>
<details><summary>Table</summary><div class="scroll" id="curvetab"></div></details>

<h2>3. Library growth</h2>
<p>Rules held after each practice game. E's management (evidence, retirement, merging, write gates) stops growth at about 25-40 rules. E-minus keeps every rule the writer produces.</p>
<div class="card"><div class="chart"><canvas id="growth"></canvas></div></div>
<h2>4. What the libraries contain at game 300</h2>
<div class="card"><div class="chart"><canvas id="comp"></canvas></div></div>
<details><summary>Table</summary><div class="scroll" id="comptab"></div></details>

<h2>5. Practice success over time</h2>
<p>Rolling first-attempt success over the previous 50 practice games. All conditions play the same games in the same order.</p>
<div class="card"><div class="chart"><canvas id="practice"></canvas></div></div>

<h2>6. OOD success by task type</h2>
<p>Most of the difference between replicates sits in one or two task types (heat, look), with only 10-18 games each.</p>
<div class="card"><div class="chart"><canvas id="kinds"></canvas></div></div>
<details><summary>Table</summary><div class="scroll" id="kindtab"></div></details>

<h2>7. The recipe lottery</h2>
<p>Each library holds one Success Process recipe per task type, written early from a few games. Its evidence (games where following it helped vs hurt) shows which replicates drew a bad recipe. E-minus can never retire or rewrite one.</p>
<div class="card scroll" id="recipes"></div>

<h2>8. How noisy is a single game?</h2>
<div class="card scroll" id="agree"></div>

<h2>9. Cost per evaluation game</h2>
<div class="card"><div class="chart" style="height:260px"><canvas id="cost"></canvas></div></div>

<h2>Takeaways</h2>
<ul>
<li>Any memory helps: on OOD, D is 9 points above C and both libraries about 18 points above C.</li>
<li>E matches E-minus with about 5x fewer rules, and its library can be read and checked.</li>
<li>Variance between replicates is mostly a recipe lottery: one bad heat or look recipe costs 5-8 evaluation games, the size of the whole E vs E-minus gap.</li>
<li>The libraries keep improving through all 300 practice games: on the same 80 games, both average about 58% after 100 games (below D's 61%), about 64% after 200, and 67-70% after 300. A third or two thirds of the practice would not have been enough to beat D.</li>
<li>Next improvement: let E rewrite a recipe once its evidence is mixed (for example neg/shown &gt; 0.4), not only when it is clearly harmful.</li>
</ul>
</main>
<script>
const D = __DATA__;
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const col = l => l.startsWith('E-minus') ? css('--em') : l.startsWith('E') ? css('--e') : l === 'D' || l.startsWith('D') ? css('--d') : css('--c');
const dash = l => /r1|-1$/.test(l) ? [6,4] : [];
const nice = s => s.replace(/^E-minus-(\d)$/, 'E-minus r$1').replace(/^E-(\d)$/, 'E r$1');
Chart.defaults.font.family = 'system-ui,-apple-system,Segoe UI,sans-serif';
Chart.defaults.color = css('--text2'); Chart.defaults.borderColor = css('--grid');
Chart.defaults.plugins.tooltip.mode = 'index'; Chart.defaults.plugins.tooltip.intersect = false;
Chart.defaults.maintainAspectRatio = false;
const pct = {min:0,max:100,ticks:{callback:v=>v+'%'}};
const table = (id, head, rows) => document.getElementById(id).innerHTML =
  '<table><tr>' + head.map(h=>`<th>${h}</th>`).join('') + '</tr>' +
  rows.map(r => '<tr>' + r.map((c,i)=>`<td class="${i?'num':''}">${c}</td>`).join('') + '</tr>').join('') + '</table>';

// tiles
const H = D.headline, avg = (a,b,s)=> ((H.find(r=>r.label==a)[s].pct + H.find(r=>r.label==b)[s].pct)/2).toFixed(1);
const t = [['C OOD', H[0].ood.pct+'%'],['D OOD', H[1].ood.pct+'%'],['E OOD (avg of 2)', avg('E r0','E r1','ood')+'%'],
  ['E-minus OOD (avg of 2)', avg('E-minus r0','E-minus r1','ood')+'%'],
  ['E rules at game 300', D.growth['E-0'].at(-1).rules+' / '+D.growth['E-1'].at(-1).rules],
  ['E-minus rules at game 300', D.growth['E-minus-0'].at(-1).rules+' / '+D.growth['E-minus-1'].at(-1).rules]];
document.getElementById('tiles').innerHTML = t.map(([a,b])=>`<div class="tile"><b>${b}</b><span>${a}</span></div>`).join('');

// 1 headline bars with CI in tooltip
for (const split of ['ood','id']) {
  new Chart(document.getElementById(split), {type:'bar', data:{labels:H.map(r=>r.label), datasets:[{
    data:H.map(r=>r[split].pct), backgroundColor:H.map(r=>col(r.label)), borderRadius:4, maxBarThickness:42}]},
    options:{plugins:{legend:{display:false}, title:{display:true,text:split==='ood'?'Unseen rooms (OOD, 134 games)':'Seen rooms (ID, 70 games)',color:css('--text')},
      tooltip:{callbacks:{label:c=>{const r=H[c.dataIndex][split];return `${r.k}/${r.n} = ${r.pct}%  (95% CI ${r.ci[0]}-${r.ci[1]}%)`}}}},
      scales:{y:pct, x:{grid:{display:false}}}}});
}
table('headtab',['Condition','OOD','OOD 95% CI','ID','ID 95% CI','tokens / game'],
  H.map(r=>[r.label,`${r.ood.k}/${r.ood.n} (${r.ood.pct}%)`,`${r.ood.ci[0]}-${r.ood.ci[1]}%`,`${r.id.k}/${r.id.n} (${r.id.pct}%)`,`${r.id.ci[0]}-${r.id.ci[1]}%`,r.tokens.toLocaleString()]));

// 2 learning curve
const P = D.curve.points, AT = D.curve.at; document.getElementById('ng').textContent = D.curve.games;
const reps = Object.keys(P).filter(k=>!('ref' in P[k]));
const cs = [];
for (const c of ['E','E-minus']) {
  const mine = reps.filter(k=>k.startsWith(c+' '));
  cs.push({label:c+' (mean of 2 replicates)', data:AT.map(a=>({x:a, y:+(mine.reduce((s,k)=>s+(P[k][a]??0),0)/mine.length).toFixed(1)})),
    borderColor:col(c), backgroundColor:col(c), borderWidth:3.5, pointRadius:5, tension:0});
  for (const k of mine) cs.push({label:k, data:AT.map(a=>({x:a, y:P[k][a] ?? null})), borderColor:col(k)+'99', backgroundColor:col(k)+'99',
    borderDash:dash(k), borderWidth:1.5, pointRadius:3, tension:0});
}
cs.push({label:'D (300 practice trajectories)', data:[{x:100,y:P.D.ref},{x:300,y:P.D.ref}], borderColor:col('D'), borderDash:[2,3], borderWidth:2, pointRadius:0});
cs.push({label:'C (no memory)', data:[{x:100,y:P.C.ref},{x:300,y:P.C.ref}], borderColor:col('C'), borderDash:[2,3], borderWidth:2, pointRadius:0});
new Chart(document.getElementById('curve'), {type:'line', data:{datasets:cs},
  options:{plugins:{tooltip:{mode:'nearest',intersect:false}}, scales:{y:{...pct,min:40,max:80,title:{display:true,text:'success on the same 80 games'}},
    x:{type:'linear',min:90,max:310,ticks:{stepSize:50,callback:v=>v%50?'':v},title:{display:true,text:'practice games the library had seen'}}}}});
table('curvetab',['Library',...AT.map(a=>'after '+a)], Object.keys(P).map(k=>[k,...AT.map(a=>('ref' in P[k]?P[k].ref:(P[k][a]??'-'))+'%')]));

// 3 growth
new Chart(document.getElementById('growth'), {type:'line', data:{datasets:Object.entries(D.growth).map(([k,v])=>({label:nice(k),
  data:v.map(p=>({x:p.game,y:p.rules})), borderColor:col(nice(k)), borderDash:dash(k), borderWidth:2, pointRadius:0}))},
  options:{parsing:true, scales:{x:{type:'linear',min:0,max:300,title:{display:true,text:'practice game'}}, y:{min:0,title:{display:true,text:'rules in library'}}}}});

// 4 composition (stacked horizontal)
const types = [...new Set(Object.values(D.composition).flatMap(o=>Object.keys(o)))];
const pal = ['#2a78d6','#eb6834','#1baf7a','#eda100','#e87ba4','#008300','#6250d6','#e34948'];
new Chart(document.getElementById('comp'), {type:'bar', data:{labels:Object.keys(D.composition).map(nice), datasets:types.map((t,i)=>({label:t,
  data:Object.values(D.composition).map(o=>o[t]||0), backgroundColor:pal[i%8], borderColor:css('--card'), borderWidth:1}))},
  options:{indexAxis:'y', plugins:{tooltip:{mode:'nearest',intersect:true}}, scales:{x:{stacked:true,title:{display:true,text:'rules'}}, y:{stacked:true}}}});
table('comptab',['Library',...types], Object.entries(D.composition).map(([k,o])=>[nice(k),...types.map(t=>o[t]||0)]));

// 5 practice rolling
const pk = Object.keys(D.practice).filter(k=>!k.includes(':'));
new Chart(document.getElementById('practice'), {type:'line', data:{labels:D.practice['D-0'].map((_,i)=>i+50), datasets:pk.map(k=>({
  label:nice(k).replace('D-0','D')+` (${D.practice[k+':total']}/300)`, data:D.practice[k], borderColor:col(nice(k)), borderDash:dash(k), borderWidth:2, pointRadius:0}))},
  options:{scales:{y:{...pct,min:30,max:100}, x:{title:{display:true,text:'practice game (window = previous 50)'},ticks:{maxTicksLimit:11}}}}});

// 6 kinds
const K = Object.keys(D.kinds), labs = H.map(r=>r.label);
new Chart(document.getElementById('kinds'), {type:'bar', data:{labels:K.map(k=>`${k} (${D.kind_n[k]})`), datasets:labs.map(l=>({label:l,
  data:K.map(k=>D.kinds[k][l]), backgroundColor:col(l), borderColor:col(l), borderWidth:/r1/.test(l)?2:0,
  ...( /r1/.test(l) ? {backgroundColor: col(l)+'66'} : {}), borderRadius:3}))},
  options:{scales:{y:pct, x:{grid:{display:false}}}}});
table('kindtab',['Task type (games)',...labs], K.map(k=>[`${k} (${D.kind_n[k]})`,...labs.map(l=>D.kinds[k][l]+'%')]));

// 7 recipes
let html = '<table><tr><th>Library</th><th>Task type</th><th>Recipe</th><th>helped</th><th>hurt</th><th>shown</th></tr>';
for (const [st, rs] of Object.entries(D.recipes)) for (const r of rs.sort((a,b)=>a.kind.localeCompare(b.kind))) {
  const bad = r.neg >= r.pos && r.shown >= 10;
  html += `<tr><td>${nice(st)}</td><td>${r.kind}</td><td>${r.text}${bad?' <b>(more harm than help)</b>':''}</td><td class="num">${r.pos}</td><td class="num">${r.neg}</td><td class="num">${r.shown}</td></tr>`;
}
document.getElementById('recipes').innerHTML = html + '</table>';

// 8 agreement
table('agree',['Pair (same 300 practice games)','games with different outcome','share'], Object.entries(D.agreement).map(([k,v])=>[k.replace(/E-minus-(\d)/g,'E-minus r$1').replace(/E-(\d)/g,'E r$1'), v.disagree+' / '+v.n, Math.round(100*v.disagree/v.n)+'%']));

// 9 cost
new Chart(document.getElementById('cost'), {type:'bar', data:{labels:H.map(r=>r.label), datasets:[{label:'tokens per evaluation game', data:H.map(r=>r.tokens), backgroundColor:H.map(r=>col(r.label)), borderRadius:4, maxBarThickness:42}]},
  options:{plugins:{legend:{display:false}}, scales:{y:{title:{display:true,text:'model tokens (in + out) per game'}}, x:{grid:{display:false}}}}});
</script></body></html>"""


def main():
    p = argparse.ArgumentParser()
    p.add_argument('study')
    p.add_argument('--curve', nargs='*', default=[])
    p.add_argument('--output', default='results/final-report/STUDY-REPORT.html')
    a = p.parse_args()
    data = build(a.study, a.curve)
    out = Path(a.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix('.json').write_text(json.dumps(data, indent=1))
    out.write_text(PAGE.replace('__DATA__', json.dumps(data)))
    print('wrote', out, 'and', out.with_suffix('.json'))


if __name__ == '__main__':
    main()
