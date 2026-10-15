"""Reproduce all retained-episode tables using the maintained repository workflow."""
import subprocess
import sys
from _paths import ROOT, arguments

args = arguments(__doc__)
subprocess.run([sys.executable, str(ROOT / "reproduce/episode_error_audit.py"),
                "--output", str(args.output)], cwd=ROOT, check=True)
