"""Build the linked traffic/QVDF/FD page and conditional inverse diagnostics."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def build(out: Path):
    from build_traffic_parameter_page import build as build_traffic
    from build_inverse_queue_speed import build as build_inverse
    from build_fd_parameter_sensitivity import build as build_sensitivity
    from parameter_diagnostic_views import attach_views

    build_traffic(out)
    build_inverse(out)
    build_sensitivity(out)
    attach_views(out)
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
    args = parser.parse_args()
    build(safe_output(args.output))
