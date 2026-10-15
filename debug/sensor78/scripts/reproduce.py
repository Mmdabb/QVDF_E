"""Reproduce detector-78 diagnostic calculations and editable vector figures.

Run from any directory. Python requires NumPy and pandas. The optional PDF build
requires pdflatex on PATH and the packages listed in reports/source/main.tex.
Published references are never overwritten.
"""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess
import sys

import numpy as np
import pandas as pd
from debug_support import prepare_output


def main():
    here = Path(__file__).resolve().parent
    bundle = here.parent
    root = here.parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=root / 'debug/output/sensor78')
    parser.add_argument('--pdf', action='store_true', help='Compile the report with pdflatex from PATH.')
    args = parser.parse_args()
    try:
        out = prepare_output(args.output_dir, root)
    except ValueError as error:
        parser.error(str(error))
    shutil.copytree(bundle / 'reports/source', out, dirs_exist_ok=True)
    for script in ('build_detector78_appendix.py', 'build_common_time_diagnostics.py',
                   'build_simple_workbook_inputs.py'):
        subprocess.run([sys.executable, str(here / script), '--output-dir',
                        str(out / 'detector78')], check=True)

    checks = []
    for ref in sorted((bundle / 'results').glob('*.csv')):
        actual = pd.read_csv(out / 'detector78' / ref.name)
        expected = pd.read_csv(ref)
        if list(actual.columns) != list(expected.columns) or actual.shape != expected.shape:
            raise AssertionError(f'Schema mismatch: {ref.name}')
        max_diff = 0.0
        for column in expected:
            a, b = actual[column], expected[column]
            if pd.api.types.is_numeric_dtype(b):
                np.testing.assert_allclose(a, b, rtol=1e-10, atol=1e-9, equal_nan=True,
                                           err_msg=f'{ref.name}: {column}')
                if a.notna().any():
                    max_diff = max(max_diff, float(np.nanmax(np.abs(a-b))))
            elif not a.fillna('').equals(b.fillna('')):
                raise AssertionError(f'Text mismatch: {ref.name}: {column}')
        checks.append({'file': ref.name, 'rows': len(actual), 'columns': len(actual.columns),
                       'maximum_absolute_numeric_difference': max_diff})
    tex_checked = []
    for ref in sorted((bundle / 'reports/source/detector78').glob('*.tex')):
        actual = out / 'detector78' / ref.name
        if actual.read_text() != ref.read_text():
            raise AssertionError(f'Figure/report source changed: {ref.name}')
        tex_checked.append(ref.name)
    audit = {'scope': 'Existing detector-78 worked example; no calibration or episode detection rerun.',
             'csv_checks': checks, 'editable_tex_sources_identical': tex_checked,
             'published_pdf_sha256': hashlib.sha256((bundle / 'reports/QVDFE_Emission_Methods_and_Results.pdf').read_bytes()).hexdigest(),
             'all_checks_passed': True, 'pdf_compiled': False}
    if args.pdf:
        engine = shutil.which('pdflatex')
        if engine is None:
            raise SystemExit('Calculations passed; install a TeX distribution and put pdflatex on PATH for --pdf.')
        for _ in range(2):
            subprocess.run([engine, '-no-shell-escape', '-interaction=nonstopmode',
                            '-halt-on-error', 'main.tex'], cwd=out, check=True,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        log = (out / 'main.log').read_text(errors='replace')
        audit['pdf_compiled'] = True
        audit['pdf_layout_warnings'] = [line for line in log.splitlines()
                                        if 'Overfull' in line or 'Missing character' in line]
        if audit['pdf_layout_warnings']:
            raise AssertionError('PDF layout check failed; inspect main.log: ' +
                                 '; '.join(audit['pdf_layout_warnings']))
        shutil.copy2(out / 'main.pdf', out / 'QVDFE_Emission_Methods_and_Results.pdf')
    (out / 'reproduction_audit.json').write_text(json.dumps(audit, indent=2), encoding='utf-8')
    print(json.dumps(audit, indent=2))


if __name__ == '__main__':
    main()
