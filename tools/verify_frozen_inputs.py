"""Check the original release's frozen data against its unchanged SHA-256 manifest.

Code and documentation have evolved since the release. This check deliberately
verifies its archived data rather than requiring old hashes for edited code.
New reporting/figure inputs carry separate provenance records.
"""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]


def verify():
    manifest = json.loads((ROOT / 'MANIFEST_SHA256.json').read_text(encoding='utf-8'))
    checked, failures = 0, []
    for name, expected in manifest.items():
        if not name.startswith(('data/frozen/', 'data/examples/')):
            continue
        path = ROOT / name
        checked += 1
        if not path.is_file():
            failures.append(f'{name}: missing')
        elif hashlib.sha256(path.read_bytes()).hexdigest() != expected['sha256']:
            failures.append(f'{name}: SHA-256 differs')
    return checked, failures


if __name__ == '__main__':
    count, errors = verify()
    print(f'{count} original data files checked; {len(errors)} differences')
    for error in errors:
        print(error)
    raise SystemExit(bool(errors))
