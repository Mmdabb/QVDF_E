"""Shared locations for optional debug workflows; reference files stay read-only."""
from pathlib import Path
import argparse
import json

ROOT = Path(__file__).resolve().parents[3]
REFERENCE = ROOT / "debug/episodes_137"
DEFAULT_OUTPUT = ROOT / "debug/output/episodes_137"


def arguments(description, *, report=False):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT,
                        help="Regenerated output directory (default: debug/output/episodes_137).")
    if report:
        parser.add_argument("--results", type=Path, default=REFERENCE / "results",
                            help="Tables used to typeset the report; defaults to bundled reference results.")
        parser.add_argument("--pdflatex", default="pdflatex",
                            help="LaTeX executable on PATH, or an explicit executable path.")
    args = parser.parse_args()
    args.output = args.output.resolve()
    # The optional workflows never replace any checked-in reference or model input.
    protected_paths = [ROOT / name for name in ("data", "src", "reproduce", "tools", "tests", ".git")]
    protected_paths += [p for p in (ROOT / "debug").iterdir() if p.is_dir() and p.name != "output"]
    if args.output.is_relative_to(ROOT / "debug") and not args.output.is_relative_to(ROOT / "debug/output"):
        raise ValueError("Inside debug/, generated outputs must stay under debug/output/.")
    for protected in protected_paths:
        if args.output == protected or args.output.is_relative_to(protected) or protected.is_relative_to(args.output):
            raise ValueError("Choose an output directory separate from source and reference data.")
    marker = args.output / ".qvdfe-episode-audit.json"
    try:
        owned = json.loads(marker.read_text(encoding="utf-8")).get("workflow") == "episode_error_audit"
    except (OSError, ValueError, AttributeError):
        owned = False
    if args.output.exists() and not args.output.is_dir():
        raise ValueError("Output destination must be a directory.")
    if args.output.exists() and any(args.output.iterdir()) and not owned:
        raise ValueError("Output directory is not owned by this workflow; choose an empty directory.")
    args.output.mkdir(parents=True, exist_ok=True)
    marker.write_text('{"workflow":"episode_error_audit"}\n', encoding="utf-8")
    (args.output / "support").mkdir(exist_ok=True)
    return args
