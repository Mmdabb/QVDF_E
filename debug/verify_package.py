"""Check the committed diagnostic package without changing reports or results."""
from pathlib import Path
import csv
import hashlib
import html
import json
import re
from urllib.parse import unquote
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DEBUG = ROOT / 'debug'


def main():
    manifest = json.loads((DEBUG / 'MANIFEST_SHA256.json').read_text(encoding='utf-8'))
    errors = []
    actual_files = {p.relative_to(ROOT).as_posix() for p in DEBUG.rglob('*')
                    if p.is_file() and not p.is_relative_to(DEBUG / 'output')
                    and '__pycache__' not in p.parts and p.suffix != '.pyc'
                    and p.name != 'MANIFEST_SHA256.json'}
    for name in sorted(actual_files - manifest['files'].keys()):
        errors.append(f'{name}: not listed in the diagnostic manifest')
    for name, record in manifest['files'].items():
        path = (ROOT / name).resolve()
        if not path.is_relative_to(DEBUG) or path.is_relative_to(DEBUG / 'output'):
            errors.append(f'{name}: outside the reference package')
        elif not path.is_file():
            errors.append(f'{name}: missing')
        elif len(path.read_bytes()) != record['bytes'] or hashlib.sha256(path.read_bytes()).hexdigest() != record['sha256']:
            errors.append(f'{name}: checksum or size differs')

    expected_rows = {
        'episodes_137/results/episode_calculations_137.csv': 137,
        'episodes_137/results/episode_review_137.csv': 137,
        'episodes_137/results/episode_pollutant_calculations_548.csv': 548,
        'episodes_137/results/average_speed_identity_check_137.csv': 137,
        'sensor78/results/common_time_series.csv': 57,
        'sensor78/results/average_weekday_profile.csv': 288,
        'full_experiment/steps/11_episode_time_series/episode_index.csv': 137,
        'full_experiment/steps/11_episode_time_series/total_reconciliation.csv': 2740,
        'case_studies/az_i10_detector141_november/results/selection_all_137.csv': 137,
        'case_studies/az_i10_detector141_november/results/selection_eligible_4.csv': 4,
        'case_studies/az_i10_detector141_november/results/emission_totals.csv': 20,
    }
    for name, expected in expected_rows.items():
        with (DEBUG / name).open(encoding='utf-8-sig', newline='') as stream:
            actual = sum(1 for _ in csv.DictReader(stream))
        if actual != expected:
            errors.append(f'{name}: {actual} rows, expected {expected}')

    for name in manifest['files']:
        path = ROOT / name
        if path.suffix == '.md':
            for target in re.findall(r'\]\(([^)]+)\)', path.read_text(encoding='utf-8')):
                target = target.strip('<>').split('#', 1)[0]
                if not target or re.match(r'^[a-z]+:', target, re.I):
                    continue
                if not (path.parent / unquote(target)).exists():
                    errors.append(f'{name}: broken link {target}')
        elif path.suffix == '.pdf' and not path.read_bytes().startswith(b'%PDF-'):
            errors.append(f'{name}: invalid PDF signature')
        elif path.suffix == '.html':
            for target in re.findall(r'(?:href|src)=[\"\']([^\"\']+)[\"\']', path.read_text(encoding='utf-8')):
                target = html.unescape(target).split('#', 1)[0]
                if not target or re.match(r'^[a-z]+:', target, re.I):
                    continue
                if not (path.parent / unquote(target)).exists():
                    errors.append(f'{name}: broken HTML link {target}')

    episode_root = DEBUG / 'full_experiment/steps/11_episode_time_series'
    with (episode_root / 'episode_index.csv').open(encoding='utf-8', newline='') as stream:
        for row in csv.DictReader(stream):
            folder = (episode_root / row['folder']).resolve()
            if not folder.is_relative_to(episode_root.resolve()):
                errors.append(f'{row["case_id"]}: episode path outside its package')
                continue
            for chart in ['traffic_profiles', 'emissions_CO2', 'emissions_NOx', 'emissions_CO', 'emissions_HC']:
                for extension in ['.png', '.svg']:
                    if not (folder / (chart+extension)).is_file():
                        errors.append(f'{row["case_id"]}: missing {chart+extension}')

    books = sorted((DEBUG / 'sensor78/workbook').glob('*.xlsx'))
    if len(books) != 1:
        errors.append('Expected one current detector-78 workbook')
    else:
        with zipfile.ZipFile(books[0]) as book:
            ns = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
            workbook = ET.fromstring(book.read('xl/workbook.xml'))
            if len(workbook.findall('m:sheets/m:sheet', ns)) != 8:
                errors.append('Workbook must contain eight sheets')
            count = 0
            for name in book.namelist():
                if name.startswith('xl/externalLinks/'):
                    errors.append('Workbook has an external-link dependency')
                if re.fullmatch(r'xl/worksheets/sheet\d+\.xml', name):
                    sheet = ET.fromstring(book.read(name))
                    count += len(sheet.findall('.//m:f', ns))
                    for cell in sheet.findall('.//m:c', ns):
                        if cell.get('t') == 'e':
                            errors.append(f'Workbook error cell {name}:{cell.get("r")}')
            if count != 14446:
                errors.append(f'Workbook has {count} formulas; expected 14446')

    print(f'{len(manifest["files"])} diagnostic files checked; {len(errors)} differences')
    for error in errors:
        print(error)
    return bool(errors)


if __name__ == '__main__':
    raise SystemExit(main())
