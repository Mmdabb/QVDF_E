"""Repository-local input and output locations for the detector-78 diagnostics."""
from pathlib import Path
import argparse
import json


MARKER = '.sensor78-generated-output.json'
OWNER = 'qvdfe-detector78-diagnostics'


def prepare_output(out, root):
    """Protect inputs/references and refuse to populate an unrelated directory."""
    out = Path(out).resolve()
    debug = root / 'debug'
    generated = debug / 'output'
    if (out == debug or debug in out.parents) and not (out == generated or generated in out.parents):
        raise ValueError('Inside debug/, generated outputs must stay under debug/output/.')
    protected = [root / name for name in ('data', '.git', 'src', 'reproduce', 'tools', 'tests')]
    protected += [p.resolve() for p in (root / 'debug').iterdir()
                  if p.is_dir() and p.name != 'output']
    if any(out == p or p in out.parents or out in p.parents for p in protected):
        raise ValueError('Output must not overlap or contain canonical inputs, source, or published references.')

    def owned(path):
        marker = path / MARKER
        try:
            return json.loads(marker.read_text(encoding='utf-8')).get('owner') == OWNER
        except (OSError, ValueError, AttributeError):
            return False

    if out.exists() and not out.is_dir():
        raise ValueError('Output destination must be a directory.')
    if out.exists() and any(out.iterdir()) and not any(owned(p) for p in (out, *out.parents)):
        raise ValueError('Output directory is nonempty and does not have the detector-78 ownership marker; choose an empty directory.')
    out.mkdir(parents=True, exist_ok=True)
    (out / MARKER).write_text(json.dumps({'owner': OWNER, 'schema': 1}), encoding='utf-8')
    return out


def locations():
    here = Path(__file__).resolve().parent
    root = here.parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path,
                        default=root / 'debug/output/sensor78/detector78')
    args = parser.parse_args()
    try:
        out = prepare_output(args.output_dir, root)
    except ValueError as error:
        parser.error(str(error))
    return here, root, out


def load_inputs(root):
    inputs = root / 'data/inputs/detector78'
    raw = json.loads((inputs / 'raw_source.json').read_text(encoding='utf-8'))
    cfg = json.loads((inputs / 'calibration_inputs.json').read_text(encoding='utf-8'))
    compact = json.loads((inputs / 'calculation_inputs.json').read_text(encoding='utf-8'))
    # Only numerical assertions use the archived results. Rates and parameters
    # are loaded from the already-published canonical input tables.
    reference = json.loads((root / 'debug/sensor78/results/regression_reference.json')
                           .read_text(encoding='utf-8'))
    reference['lookup_rates'] = [
        {'OpModeID': row['source_operating_mode'],
         **{p: row[f'{p}_g_per_veh_h'] for p in ('CO2', 'NOx', 'CO', 'HC')}}
        for row in compact['rate_table']
    ]
    return raw, cfg, reference
