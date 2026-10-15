"""Remove Excel's optional local-directory metadata without rewriting cell data.

This utility does not recalculate, reserialize worksheets, or change formulas.
The original and published uncompressed ZIP entries are compared before success.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import zipfile
from workbook_paths import validate_output_paths


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    validate_output_paths([("output workbook", args.output), ("report", args.report)],
                          [("source workbook", args.source)])
    source_bytes = args.source.read_bytes()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    pattern = rb'<mc:AlternateContent\b[^>]*>\s*<mc:Choice\b[^>]*>\s*<x15ac:absPath\b[^>]*/>\s*</mc:Choice>\s*</mc:AlternateContent>'
    removed = 0
    with zipfile.ZipFile(args.source) as source, zipfile.ZipFile(args.output, "w") as target:
        for info in source.infolist():
            data = source.read(info.filename)
            if info.filename == "xl/workbook.xml":
                data, removed = re.subn(pattern, b"", data)
            target.writestr(info, data)
    with zipfile.ZipFile(args.source) as source, zipfile.ZipFile(args.output) as target:
        changed = [name for name in source.namelist() if source.read(name) != target.read(name)]
        same_entries = source.namelist() == target.namelist()
        unchanged_payload = same_entries and all(name == "xl/workbook.xml" for name in changed)
        private_path_hits = [name for name in target.namelist() if name.endswith(".xml")
                             and re.search(rb"[A-Za-z]:[/\\]Users[/\\]", target.read(name))]
    report = {
        "source_name": args.source.name,
        "published_name": args.output.name,
        "source_sha256": digest(source_bytes),
        "published_sha256": digest(args.output.read_bytes()),
        "optional_local_directory_blocks_removed": removed,
        "changed_zip_entries": changed,
        "all_worksheet_formula_cache_style_and_other_entries_unchanged": unchanged_payload,
        "absolute_user_path_xml_hits": private_path_hits,
        "scope": "Only Excel's optional absPath publishing metadata is removed; no recalculation or formula edits.",
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not unchanged_payload or private_path_hits:
        raise SystemExit("Publication metadata audit failed.")


if __name__ == "__main__":
    main()
