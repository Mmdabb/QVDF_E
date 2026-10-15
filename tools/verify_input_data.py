"""Verify the empirical and worked-example input bundle, including reused frozen files."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]


def verify():
    manifest = json.loads((ROOT / 'data/inputs/MANIFEST_SHA256.json').read_text(encoding='utf-8'))
    failures = []
    for name, record in manifest['files'].items():
        path = (ROOT / name).resolve()
        if not path.is_relative_to(ROOT / 'data'):
            failures.append(f'{name}: outside data directory')
        elif not path.is_file():
            failures.append(f'{name}: missing')
        elif path.stat().st_size != record['bytes'] or hashlib.sha256(path.read_bytes()).hexdigest() != record['sha256']:
            failures.append(f'{name}: checksum or size differs')
    return len(manifest['files']), failures


if __name__ == '__main__':
    count, errors = verify()
    print(f'{count} input files checked; {len(errors)} differences')
    for error in errors:
        print(error)
    raise SystemExit(bool(errors))
