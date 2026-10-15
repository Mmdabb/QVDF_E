"""Protect published data and source artifacts from diagnostic output writes."""
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[3]
WORKING_OUTPUT = REPOSITORY / "debug/output"


def same_file(left, right):
    left, right = Path(left).resolve(), Path(right).resolve()
    return left == right or (left.exists() and right.exists() and left.samefile(right))


def validate_output_paths(outputs, inputs):
    """Validate all destinations before creating directories or writing files."""
    destinations = [(label, Path(path).resolve()) for label, path in outputs]
    sources = [(label, Path(path).resolve()) for label, path in inputs]
    for index, (label, path) in enumerate(destinations):
        for source_label, source in sources:
            if same_file(path, source):
                raise SystemExit(f"Unsafe {label}: destination collides with {source_label}.")
        for other_label, other in destinations[:index]:
            if same_file(path, other):
                raise SystemExit(f"Unsafe {label}: destination collides with {other_label}.")
        repository = REPOSITORY.resolve()
        # Do not resolve the allowed root through a junction into references.
        working = repository / "debug/output"
        inside_repository = path == repository or repository in path.parents
        inside_working = path != working and working in path.parents
        if inside_repository and not inside_working:
            raise SystemExit(f"Unsafe {label}: repository reference/source folders are read-only. Use debug/output/ or an external working directory.")
