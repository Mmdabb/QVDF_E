"""Check the committed diagnostic package without changing reports or results."""
from pathlib import Path
import csv
import hashlib
import html
from html.parser import HTMLParser
import json
import re
from urllib.parse import unquote
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DEBUG = ROOT / 'debug'


class DashboardMarkup(HTMLParser):
    """Inspect actual elements, without counting CSS selectors or script text."""
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.tables = 0
        self.current_pages = 0
        self.math_elements = 0
        self.script_sources = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        self.tables += tag == 'table'
        self.math_elements += tag == 'math'
        self.current_pages += values.get('aria-current', '').lower() == 'page'
        if tag == 'script' and values.get('src'):
            self.script_sources.append(values['src'])

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)


def verify_dashboard_html(path, errors, *, current_page=True):
    """Check layout and every native MathML expression without executing HTML."""
    name = path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path)
    if not path.is_file():
        errors.append(f'{name}: missing dashboard HTML page')
        return
    document = path.read_text(encoding='utf-8')
    markup = DashboardMarkup()
    markup.feed(document)
    markup.close()
    if markup.tables != 1:
        errors.append(f'{name}: {markup.tables} tables, expected exactly one')
    if current_page and markup.current_pages != 1:
        errors.append(f'{name}: {markup.current_pages} aria-current="page" elements, expected exactly one')
    formulas = re.findall(r'<math\b[^>]*>.*?</math\s*>', document, flags=re.I | re.S)
    if not markup.math_elements or len(formulas) != markup.math_elements:
        errors.append(f'{name}: missing native MathML or unclosed math element')
    namespace = 'http://www.w3.org/1998/Math/MathML'
    child_counts = {'mfrac': 2, 'msub': 2, 'msup': 2, 'mover': 2, 'msubsup': 3}
    for number, formula in enumerate(formulas, 1):
        try:
            expression = ET.fromstring(formula)
        except ET.ParseError as error:
            errors.append(f'{name}: MathML expression {number} is not valid XML: {error}')
            continue
        if expression.tag != '{'+namespace+'}math':
            errors.append(f'{name}: MathML expression {number} lacks the native MathML namespace')
        for element in expression.iter():
            local = element.tag.rsplit('}', 1)[-1]
            if local in child_counts and len(element) != child_counts[local]:
                errors.append(f'{name}: MathML expression {number}: {local} has {len(element)} children, expected {child_counts[local]}')
    for source in markup.script_sources:
        if re.match(r'^(?:[a-z]+:)?//', source, re.I) or re.search(r'mathjax|katex|temml', source, re.I):
            errors.append(f'{name}: external script or math-renderer dependency: {source}')
    for script in re.findall(r'<script\b[^>]*>(.*?)</script\s*>', document, flags=re.I | re.S):
        if re.search(r'\b(?:MathJax|katex|temml)\b', script, re.I):
            errors.append(f'{name}: script-based math renderer instead of native MathML')


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
        'full_experiment/steps/11_episode_time_series/all_error_metrics.csv': 12330,
        'full_experiment/steps/11_episode_time_series/traffic_parameters.csv': 137,
        'full_experiment/steps/11_episode_time_series/inverse_queue_speed.csv': 274,
        'full_experiment/steps/11_episode_time_series/inverse_queue_speed_candidates.csv': 1304,
        'full_experiment/steps/11_episode_time_series/inverse_queue_speed_roots.csv': 377,
        'full_experiment/steps/11_episode_time_series/inverse_queue_speed_intervals.csv': 1452,
        'full_experiment/steps/11_episode_time_series/fd_parameter_sensitivity.csv': 274,
        'full_experiment/steps/11_episode_time_series/fd_parameter_sensitivity_expanded.csv': 274,
        'full_experiment/steps/11_episode_time_series/fd_bound_sensitivity_summary.csv': 4,
        'full_experiment/steps/11_episode_time_series/fd_capacity_comparison.csv': 548,
        'capacity_sensitivity/fixed_traffic_comparison.csv': 1096,
        'capacity_sensitivity/capacity_sweep.csv': 1918,
        'capacity_sensitivity/detector_capacity_audit.csv': 352,
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
    root_pages = {'index.html', 'traffic_parameters.html', 'inverse_emissions.html',
                  'inverse_fd.html', 'fd_sensitivity.html', 'fd_summary.html',
                  'fd_capacity_comparison.html'}
    actual_root_pages = {p.name for p in episode_root.glob('*.html')}
    if actual_root_pages != root_pages:
        errors.append(f'{episode_root.relative_to(ROOT)}: root HTML pages differ; missing={sorted(root_pages-actual_root_pages)}, unexpected={sorted(actual_root_pages-root_pages)}')
    for name in sorted(root_pages):
        verify_dashboard_html(episode_root/name, errors)
    episode_pages = {'index.html', 'emissions_CO2.html', 'emissions_NOx.html',
                     'emissions_CO.html', 'emissions_HC.html'}
    with (episode_root / 'episode_index.csv').open(encoding='utf-8', newline='') as stream:
        for row in csv.DictReader(stream):
            folder = (episode_root / row['folder']).resolve()
            if not folder.is_relative_to(episode_root.resolve()):
                errors.append(f'{row["case_id"]}: episode path outside its package')
                continue
            actual_episode_pages = {p.name for p in folder.glob('*.html')}
            if actual_episode_pages != episode_pages:
                errors.append(f'{row["case_id"]}: expected exactly five episode HTML pages; missing={sorted(episode_pages-actual_episode_pages)}, unexpected={sorted(actual_episode_pages-episode_pages)}')
            for name in sorted(episode_pages):
                verify_dashboard_html(folder/name, errors)
            with (folder / 'error_metrics.csv').open(encoding='utf-8', newline='') as metrics:
                if sum(1 for _ in csv.DictReader(metrics)) != 90:
                    errors.append(f'{row["case_id"]}: expected 90 error metrics')
            for chart in ['traffic_profiles', 'emissions_CO2', 'emissions_NOx', 'emissions_CO', 'emissions_HC']:
                for extension in ['.png', '.svg']:
                    if not (folder / (chart+extension)).is_file():
                        errors.append(f'{row["case_id"]}: missing {chart+extension}')
    verify_dashboard_html(DEBUG/'capacity_sensitivity/report.html', errors, current_page=False)

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
