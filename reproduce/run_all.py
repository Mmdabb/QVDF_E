"""Run every supported reproduction entry and compare its outputs with the frozen results and the paper's figures.

    python reproduce/run_all.py            # all entries
    python reproduce/run_all.py --skip-figures
    python reproduce/run_all.py --strict        # also fail when a figure differs from the paper's

Outputs go to reproduce/output/ only. Comparisons:
  * calculations and audit: every CSV, JSON and TeX file written is compared with its frozen counterpart
    (numbers with rtol 1e-9 and atol 1e-12; JSON 'inputs' blocks, which hold file paths and hashes, are skipped);
  * figures: when a copy of the published figures is available (folder given by the environment variable
    QVDFE_PAPER_FIGS), each regenerated PDF is rendered and compared with it pixel by pixel; otherwise the figure is
    only regenerated.
Exit status is nonzero if any entry fails or any calculation/audit file differs. Figure comparisons are
informational unless --strict is given (renderer versions change pixels; Figs. 4 and D1 have an earlier layout).
"""
from pathlib import Path
import argparse
import json
import subprocess
import sys
import time

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 'lib'))
from _paths import ROOT, FROZEN, OUT  # noqa: E402


def first(*paths):
    return next((p for p in paths if p.exists()), paths[-1])


import os
PAPER_FIGS = Path(os.environ.get('QVDFE_PAPER_FIGS', ROOT / 'published_figures'))   # optional copy of the published figures

ENTRIES = [   # (script, [(figure file stem, paper item)])
    ('fig01_overview.py', [('fig1_overview', 'Fig. 1')]),
    ('fig02_rates_and_gamma.py', [('fig1_emission_rate', 'Fig. 2'), ('fig_gamma_behavior', 'Fig. 5')]),
    ('fig03_shockwave.py', [('fig2_shockwave_bottleneck', 'Fig. 3')]),
    ('fig04_figD1_queue_and_scheduling.py', [('fig3_fluid_queue', 'Fig. 4'), ('fig4_scheduling', 'Fig. D1')]),
    ('fig05_transition.py', [('fig13_transition', 'Fig. 6')]),
    ('fig07_paired_episode.py', [('fig7_paired_episode', 'Fig. 8')]),
    ('fig09_fig10_fig11_fig12_evidence.py', [('fig8_calibration', 'Fig. 10'), ('fig9_emission_comparison', 'Fig. 11'),
                                             ('fig5_gamma_progression', 'Fig. 12'), ('fig10_emission_elasticity', 'Fig. 13')]),
    ('figE1_two_route.py', [('fig12_pigou_network', 'Fig. E1')]),
    ('calc_cohort_admissibility.py', []),
    ('calc_corridor_admissibility.py', []),
    ('calc_daytime_period.py', []),
    ('audit_numerics.py', []),
    ('current_reporting.py', []),
]
# frozen counterparts of the calculation and audit outputs
COMPARE_DIRS = [(OUT / 'calculations', [FROZEN / 'applicability']), (OUT / 'audit', [FROZEN / 'calibration' / 'audit'])]


def same_json(a, b, path=''):
    if isinstance(a, dict) and isinstance(b, dict):
        bad = []
        for k in set(a) | set(b):
            if k == 'inputs':
                continue
            if k not in a or k not in b:
                bad.append(f'{path}/{k} missing')
            else:
                bad += same_json(a[k], b[k], f'{path}/{k}')
        return bad
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return [f'{path} length {len(a)} vs {len(b)}']
        return [x for i, (u, v) in enumerate(zip(a, b)) for x in same_json(u, v, f'{path}[{i}]')]
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        return [] if np.isclose(a, b, rtol=1e-9, atol=1e-12, equal_nan=True) else [f'{path} {a} vs {b}']
    return [] if a == b else [f'{path} {str(a)[:60]} vs {str(b)[:60]}']


def same_csv(a, b):
    x, y = pd.read_csv(a, low_memory=False), pd.read_csv(b, low_memory=False)
    if list(x.columns) != list(y.columns) or len(x) != len(y):
        return [f'shape/columns {x.shape} vs {y.shape}']
    bad = []
    for c in x.columns:
        u, v = x[c], y[c]
        if pd.api.types.is_numeric_dtype(u) and pd.api.types.is_numeric_dtype(v):
            if not np.allclose(u.to_numpy(float), v.to_numpy(float), rtol=1e-9, atol=1e-12, equal_nan=True):
                bad.append(f'column {c}')
        elif not u.astype(str).equals(v.astype(str)):
            bad.append(f'column {c}')
    return bad


def compare_outputs(since):
    rows = []
    for out_dir, refs in COMPARE_DIRS:
        for f in sorted(out_dir.glob('*')):
            if f.stat().st_mtime < since or f.suffix not in ('.csv', '.json', '.tex'):
                continue
            ref = next((r / f.name for r in refs if (r / f.name).exists()), None)
            if ref is None:
                rows.append((f'{out_dir.name}/{f.name}', 'no frozen counterpart (informational)', True))
                continue
            if f.suffix == '.csv':
                bad = same_csv(f, ref)
            elif f.suffix == '.json':
                bad = same_json(json.loads(f.read_text(encoding='utf-8')), json.loads(ref.read_text(encoding='utf-8')))
            else:
                bad = [] if f.read_text(encoding='utf-8').strip() == ref.read_text(encoding='utf-8').strip() else ['text differs']
            rows.append((f'{out_dir.name}/{f.name}', 'identical' if not bad else 'DIFFERS: ' + '; '.join(bad[:3]), not bad))
    return rows


def figure_diff(stem):
    import pypdfium2 as pdfium
    new, old = OUT / 'figs' / f'{stem}.pdf', PAPER_FIGS / f'{stem}.pdf'
    if not new.exists():
        return 'not written', False
    if not old.exists():
        return 'regenerated (no published copy to compare)', True

    def raster(p):
        page = pdfium.PdfDocument(str(p))[0]
        return np.asarray(page.render(scale=72 / 72).to_pil().convert('L'), float) / 255

    a, b = raster(new), raster(old)
    if a.shape != b.shape:
        return f'size differs {a.shape} vs {b.shape}', False
    d = float(np.abs(a - b).mean())
    return (f'mean grey difference {d:.4f}' + ('' if d < 0.01 else ' (differs: inspect)')), d < 0.01


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--skip-figures', action='store_true')
    ap.add_argument('--strict', action='store_true', help='count figure differences as failures')
    a = ap.parse_args()
    start = time.time() - 1
    results, ok_all = [], True
    for script, stems in ENTRIES:
        if a.skip_figures and stems:
            continue
        t0 = time.time()
        p = subprocess.run([sys.executable, str(HERE / script)], capture_output=True, text=True)
        ok = p.returncode == 0
        ok_all &= ok
        results.append((script, 'PASS' if ok else 'FAIL', f'{time.time() - t0:.0f} s'))
        if not ok:
            print(p.stdout[-1500:], p.stderr[-2500:])
        for s, item in stems:
            msg, good = figure_diff(s)
            if a.strict:
                ok_all &= good
            results.append((f'  {item} ({s}.pdf)', msg, '' if a.strict else '[informational]'))
    print(f"{'entry':48s} result")
    for r in results:
        print(f'{r[0]:48s} {r[1]} {r[2]}')
    print('\ncalculation and audit outputs versus the frozen files:')
    for name, msg, good in compare_outputs(start):
        ok_all &= good
        print(f'  {name:60s} {msg}')
    print('\nALL PASS' if ok_all else '\nSOME CHECKS FAILED')
    (OUT / 'run_all_summary.json').write_text(json.dumps({'entries': results, 'all_pass': bool(ok_all)}, indent=1), encoding='utf-8')
    sys.exit(0 if ok_all else 1)


if __name__ == '__main__':
    main()
