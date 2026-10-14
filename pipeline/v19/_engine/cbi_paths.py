"""Shared path helpers for the refreshed CBI package."""

from __future__ import annotations

from pathlib import Path


def package_root() -> Path:
    """Return the project root that contains ``codes`` and ``datasets``."""
    return Path(__file__).resolve().parents[2]


def project_root_from_cwd(cwd: Path | None = None) -> Path:
    """Return project root whether a notebook runs from root or ``codes/``."""
    cwd = Path.cwd() if cwd is None else Path(cwd)
    return cwd.parent if cwd.name == "codes" else cwd


def project_path(value, project_root: Path | None = None) -> Path | None:
    """Resolve a project-relative path while preserving absolute paths."""
    if value is None:
        return None
    root = project_root_from_cwd() if project_root is None else Path(project_root)
    path = Path(value)
    return path if path.is_absolute() else root / path


def safe_path_name(value) -> str:
    """Return a filesystem-safe folder name for dataset-scoped outputs."""
    name = Path(str(value)).name if value is not None else ""
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in name.strip())
    safe = safe.strip("._")
    return safe or "dataset"


def dataset_name_from_path(value) -> str | None:
    """Infer the dataset name from a Stage 0 dataset folder/path value."""
    if value is None:
        return None
    return safe_path_name(value)


def default_output_root(project_root: Path | None = None) -> Path:
    """Return the default CBI output root."""
    root = package_root() if project_root is None else Path(project_root)
    return root / "cbi_outputs"


def stage_output_dir(
    stage_folder: str,
    out_root=None,
    project_root: Path | None = None,
    dataset_name: str | None = None,
) -> Path:
    """Return an output directory for a named stage folder."""
    root = default_output_root(project_root) if out_root is None else project_path(out_root, project_root)
    out_dir = Path(root) / stage_folder
    if dataset_name:
        out_dir = out_dir / safe_path_name(dataset_name)
    return out_dir
