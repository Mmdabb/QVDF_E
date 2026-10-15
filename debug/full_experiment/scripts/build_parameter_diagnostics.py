"""Build the linked traffic/QVDF/FD page and conditional inverse diagnostics."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[3]


def rebase_analysis_links(out: Path, source: Path | None = None):
    """Keep the separate report reachable from working and published layouts."""
    source = (source or ROOT/'debug/capacity_sensitivity').resolve()
    pattern = re.compile(r'(href=[\"\'])(?:\.\./)+(?:output/)?capacity_sensitivity/([^\"\']+)([\"\'])')
    for page in out.rglob('*.html'):
        content = page.read_text(encoding='utf-8')
        def replace(match):
            relative = os.path.relpath(source/match[2], page.parent).replace('\\', '/')
            return match[1]+relative+match[3]
        updated = pattern.sub(replace, content)
        if updated != content:
            page.write_text(updated, encoding='utf-8', newline='\n')


def build(out: Path, capacity_source: Path | None = None):
    from build_traffic_parameter_page import build as build_traffic
    from build_inverse_queue_speed import build as build_inverse
    from build_fd_parameter_sensitivity import build as build_sensitivity
    from parameter_diagnostic_views import attach_views
    from build_capacity_comparison_page import build as build_capacity_page

    build_traffic(out)
    build_inverse(out)
    build_sensitivity(out)
    attach_views(out)
    build_capacity_page(out, capacity_source)
    rebase_analysis_links(out, capacity_source)
    audit_path = out/'traffic_parameter_verification.json'
    audit = json.loads(audit_path.read_text(encoding='utf-8'))
    audit['interpretation']['inverse_analysis'] = 'Provided separately in inverse_queue_speed_verification.json and fd_sensitivity_verification.json; the traffic audit above verifies only the source parameter join.'
    audit_path.write_text(json.dumps(audit, indent=2, ensure_ascii=False)+'\n', encoding='utf-8', newline='\n')
    print("Linked traffic, QVDF, inverse-emission and FD sensitivity page complete.", flush=True)


def safe_output(path):
    out = Path(path).resolve()
    if ROOT.resolve().is_relative_to(out) or (out.is_relative_to(ROOT.resolve()) and not out.is_relative_to(ROOT/'debug/output')):
        raise ValueError("Use debug/output/ or a separate working directory; reference files are protected.")
    marker = out/'.episode-time-series-trace.json'
    if out.exists() and (not out.is_dir() or (any(out.iterdir()) and not marker.is_file())):
        raise ValueError("Use an empty directory or the episode generator's owned output directory.")
    out.mkdir(parents=True, exist_ok=True)
    if not marker.exists():
        marker.write_text(json.dumps({'owner':'qvdfe-parameter-diagnostics'})+'\n',encoding='utf-8')
    return out


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'debug/output/episode_time_series')
    parser.add_argument('--capacity-source',type=Path,default=None,help='Reviewed or regenerated capacity sensitivity directory')
    args = parser.parse_args()
    build(safe_output(args.output), args.capacity_source)
