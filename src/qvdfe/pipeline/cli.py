"""Portable entry point for the retained empirical experiment workflow."""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
from pathlib import Path

from qvdfe.paths import repo_root

BASELINE_FILES = (
    "traffic_panel.csv.gz", "sensor_parameters.csv", "episodes_detected.csv",
    "detector_fd_calibration.csv", "cubic_rate_coefficients.csv",
    "input_sha256.json", "fd_estimation_protocol.json", "episode_results_v2.csv",
)
RATE_FILES = ("input_vehicle_type.csv", "input_vehicle_emission_rate.csv")
TRACK_FILES = ("traffic_panel.csv.gz", "sensor_parameters.csv", "episodes_detected.csv", "cubic_rate_coefficients.csv")
MODEL_FILES = ("sensor_parameters.csv", "episode_results_v2.csv", "cubic_rate_coefficients.csv")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require_files(folder: Path, names) -> None:
    missing = [str(folder / name) for name in names if not (folder / name).is_file()]
    if missing:
        raise FileNotFoundError("Required input files are missing:\n  " + "\n  ".join(missing))


def manifest_sources(data_root: Path, baseline: Path) -> list[Path]:
    """Resolve the original inputs so output guards protect files, not just folders."""
    manifest = json.loads((baseline / "input_sha256.json").read_text(encoding="utf-8-sig"))
    if not isinstance(manifest, list) or not manifest:
        raise ValueError("input_sha256.json must contain a nonempty list of source paths and SHA-256 values")
    sources = []
    for row in manifest:
        relative = Path(row["path"].replace("\\", "/"))
        source = (data_root / relative).resolve()
        if relative.is_absolute() or not source.is_relative_to(data_root.resolve()):
            raise ValueError("Source-manifest paths must be relative to --data-root")
        sources.append(source)
    return sources


def check_inputs(data_root: Path, baseline: Path, emission_input: Path) -> dict:
    """Validate external inputs, without copying or changing them."""
    require_files(baseline, BASELINE_FILES)
    require_files(emission_input, RATE_FILES)
    if not (baseline / "repository_reference").is_dir():
        raise FileNotFoundError("Baseline requires its repository_reference directory")
    manifest = json.loads((baseline / "input_sha256.json").read_text(encoding="utf-8-sig"))
    if not isinstance(manifest, list) or not manifest:
        raise ValueError("input_sha256.json must contain a nonempty list of source paths and SHA-256 values")
    verified = []
    for row in manifest:
        relative = Path(row["path"].replace("\\", "/"))
        source = (data_root / relative).resolve()
        if relative.is_absolute() or not source.is_relative_to(data_root.resolve()):
            raise ValueError("Source-manifest paths must be relative to --data-root")
        require_files(source.parent, [source.name])
        if sha256(source) != row["sha256"]:
            raise ValueError("Source hash mismatch: " + str(relative))
        verified.append(relative.as_posix())
    return {
        "original_source_hashes_verified": len(verified),
        "source_paths": verified,
        "baseline_sha256": {name: sha256(baseline / name) for name in BASELINE_FILES},
        "emission_input_sha256": {name: sha256(emission_input / name) for name in RATE_FILES},
        "raw_reconstruction": False,
        "entry_level": "Recorded preprocessed traffic baseline with verified source hashes",
    }


def protect_output(output: Path, inputs) -> None:
    """Reject nested/ancestor input destinations and the repository's frozen data."""
    output = output.resolve()
    frozen = repo_root() / "data" / "frozen"
    for path in [*inputs, frozen]:
        path = path.resolve()
        if output == path or output.is_relative_to(path) or path.is_relative_to(output):
            raise ValueError("Output must be separate from input/frozen directories: " + str(path))


def prepare_output(output: Path, kind: str) -> None:
    """Avoid silently taking ownership of an unrelated existing directory."""
    marker = output / ".qvdfe-pipeline-run.json"
    if output.exists() and any(output.iterdir()) and not marker.is_file():
        raise ValueError("Output is not a workflow-owned directory; choose a new output directory")
    output.mkdir(parents=True, exist_ok=True)
    if marker.is_file():
        prior = json.loads(marker.read_text(encoding="utf-8"))
        if prior["kind"] != kind:
            raise ValueError("Output belongs to a different workflow command")
    marker.write_text(json.dumps({"kind": kind, "workflow": "qvdfe.pipeline"}, indent=2) + "\n", encoding="utf-8")


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="python -m qvdfe.pipeline", description=__doc__)
    commands = ap.add_subparsers(dest="command", required=True)
    for name in ("empirical", "check-inputs"):
        sub = commands.add_parser(name)
        sub.add_argument("--data-root", type=Path, required=True, help="Root resolving relative paths in the baseline input_sha256.json")
        sub.add_argument("--baseline", type=Path, required=True, help="External recorded preprocessed traffic baseline")
        sub.add_argument("--emission-input", type=Path, required=True, help="Directory containing the two MOVES-derived input CSV files")
        if name == "empirical":
            sub.add_argument("--stage", choices=["data", "daily", "average", "metrics", "audit", "all"], default="all")
            sub.add_argument("--output", type=Path, required=True)
            sub.add_argument("--bootstrap", type=int, default=400)
    sub = commands.add_parser("surrogate", help="Fit signed-power compression from full calibrated parameter cards")
    sub.add_argument("--data", type=Path, required=True, help="Average-weekday calibration directory")
    sub.add_argument("--output", type=Path, required=True)
    sub = commands.add_parser("pigou", help="Solve full and compressed CO2-generalized routing costs")
    sub.add_argument("--data", type=Path, required=True)
    sub.add_argument("--surrogate", type=Path, required=True)
    sub.add_argument("--output", type=Path, required=True)
    sub.add_argument("--corridor", default="AZ_I10_W")
    sub.add_argument("--period", default="MD", choices=["AM", "MD", "PM", "NT"])
    return ap


def main(argv=None) -> None:
    ap = parser()
    args = ap.parse_args(argv)
    for key, value in vars(args).items():
        if isinstance(value, Path):
            setattr(args, key, value.expanduser().resolve())
    if args.command == "check-inputs":
        print(json.dumps(check_inputs(args.data_root, args.baseline, args.emission_input), indent=2))
        return
    inputs = [args.baseline, args.emission_input] if args.command == "empirical" else [args.data]
    if args.command == "empirical":
        inputs.extend(manifest_sources(args.data_root, args.baseline))
    if args.command == "pigou":
        inputs.append(args.surrogate)
    protect_output(args.output, inputs)
    if args.command == "empirical":
        if args.bootstrap < 2:
            ap.error("--bootstrap must be at least 2 (400 replicates reproduce the paper protocol)")
        if args.stage in ("data", "all"):
            verified = check_inputs(args.data_root, args.baseline, args.emission_input)
        elif args.stage in ("daily", "average"):
            require_files(args.output / ("daily_validation" if args.stage == "daily" else "average_weekday"), TRACK_FILES)
        if args.stage in ("average", "all"):
            require_files(args.emission_input, RATE_FILES)
        prepare_output(args.output, "empirical")
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                            handlers=[logging.StreamHandler(), logging.FileHandler(args.output / "run.log", encoding="utf-8")])
        if args.stage in ("data", "all"):
            (args.output / "input_contract_verified.json").write_text(json.dumps(verified, indent=2) + "\n", encoding="utf-8")
            from ._engine import data_preparation
            data_preparation.run(args.data_root, args.output, args.baseline)
        from ._engine import calibration
        if args.stage in ("daily", "all"):
            calibration.run_daily(args.data_root, args.output, args.bootstrap)
        if args.stage in ("average", "all"):
            calibration.run_average(args.data_root, args.output, args.bootstrap, args.emission_input)
        if args.stage in ("audit", "all"):
            calibration.audit(args.data_root, args.output, args.baseline)
        if args.stage == "metrics":
            calibration.refresh_metrics(args.output, args.bootstrap)
    elif args.command == "surrogate":
        require_files(args.data, MODEL_FILES)
        prepare_output(args.output, "surrogate")
        from .surrogate import run
        run(args.data, args.output)
    else:
        require_files(args.data, ["episode_results_v2.csv"])
        require_files(args.surrogate, ["surrogate_coefficients.csv", "surrogate_specification.json", "surrogate_curves.csv"])
        prepare_output(args.output, "pigou")
        from .pigou import run
        run(args.surrogate, args.data, args.output, args.corridor, args.period)
