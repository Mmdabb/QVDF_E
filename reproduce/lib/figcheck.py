"""Shared figure style (figure_polish/polish_style.py; Cassidy-like: black/grey line work, one blue accent, direct labels, no in-figure notes)
and an overlap check: every text, title and legend box is tested against every plotted line, marker and
other text box. Shaded areas (fill_between, axvspan) are not obstacles; text may sit on them."""
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.lines import Line2D
from matplotlib.collections import PathCollection
from matplotlib.text import Annotation, Text

import os as _os, shutil as _shutil, subprocess as _subprocess


def _tex_gyre_dirs():
    """Folders that may hold the TeX Gyre Termes fonts: $TEXGYRE_DIR, kpsewhich, common TeX locations."""
    dirs = [Path(_os.environ['TEXGYRE_DIR'])] if _os.environ.get('TEXGYRE_DIR') else []
    if _shutil.which('kpsewhich'):
        try:
            hit = _subprocess.run(['kpsewhich', 'texgyretermes-regular.otf'], capture_output=True, text=True, timeout=20).stdout.strip()
            if hit:
                dirs.append(Path(hit).parent)
        except Exception:
            pass
    dirs += [Path.home() / 'AppData/Local/Programs/MiKTeX/fonts/opentype/public/tex-gyre',
             Path('/usr/share/texmf/fonts/opentype/public/tex-gyre'), Path('/usr/share/texlive/texmf-dist/fonts/opentype/public/tex-gyre')]
    return dirs


for f in ["texgyretermes-regular.otf", "texgyretermes-italic.otf", "texgyretermes-bold.otf"]:
    for d in _tex_gyre_dirs():
        if (d / f).exists():
            font_manager.fontManager.addfont(str(d / f))
import sys as _sys
for _d in (Path(__file__).resolve().parent,):
    if (_d / "polish_style.py").exists():
        _sys.path.insert(0, str(_d))
import polish_style as _P          # shared figure style (figure_polish/polish_style.py)
INK, GRAY, LIGHT, BLUE = _P.INK, _P.MID, _P.LIGHT, _P.ACCENT
STYLE = _P.RC
_P.apply()


def _line_points(ax, ln, step=1.5):
    """Line vertices in display pixels, densified every `step` px (markers only: the vertices)."""
    x, y = ln.get_xdata(orig=False), ln.get_ydata(orig=False)
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() == 0:
        return np.empty((0, 2))
    tr = ln.get_transform()
    P = tr.transform(np.c_[x[ok], y[ok]])
    if ln.get_linestyle() in ("None", "none", "", " "):
        return P
    out = [P[:1]]
    for a, b in zip(P[:-1], P[1:]):
        n = max(int(np.hypot(*(b - a)) / step), 1)
        out.append(a + (b - a) * np.linspace(0, 1, n + 1)[1:, None])
    return np.vstack(out)


def check_overlaps(fig, ignore_gids=("ref",), pad=0.5, verbose=True):
    """Return a list of (text, obstacle) overlaps. Lines with gid in ignore_gids are skipped."""
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    issues = []
    boxes = []
    for ax in fig.axes:
        texts = list(ax.texts) + [ax.title, ax._left_title, ax._right_title]
        texts = [t for t in texts if t.get_visible() and t.get_text().strip()]
        items = [(t.get_text(), Text.get_window_extent(t, r)) for t in texts]   # text only, not the arrow
        leg = ax.get_legend()
        if leg is not None:
            items.append(("<legend>", leg.get_window_extent(r)))
        for lab in ax.get_xticklabels() + ax.get_yticklabels():
            if lab.get_visible() and lab.get_text().strip():
                boxes.append((f"tick:{lab.get_text()}", lab.get_window_extent(r), ax))
        for lab in (ax.xaxis.label, ax.yaxis.label):
            if lab.get_visible() and lab.get_text().strip():
                boxes.append((f"axislabel:{lab.get_text()}", lab.get_window_extent(r), ax))
        obst = []
        for k, ln in enumerate(ax.lines):
            if ln.get_gid() in ignore_gids or not ln.get_visible():
                continue
            obst.append((f"line{k}", _line_points(ax, ln)))
        for k, c in enumerate(ax.collections):
            if isinstance(c, PathCollection) and c.get_gid() not in ignore_gids:
                obst.append((f"markers{k}", c.get_offset_transform().transform(c.get_offsets())))
        for name, bb in items:
            b = bb.padded(-pad)
            for oname, P in obst:
                if len(P):
                    inside = (P[:, 0] > b.x0) & (P[:, 0] < b.x1) & (P[:, 1] > b.y0) & (P[:, 1] < b.y1)
                    if inside.any():
                        issues.append((name, oname, int(inside.sum())))
            boxes.append((name, bb, ax))
    # text-text overlaps (all axes, including tick labels)
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            (n1, b1, a1), (n2, b2, a2) = boxes[i], boxes[j]
            if n1.startswith(("tick:", "axislabel:")) and n2.startswith(("tick:", "axislabel:")) and a1 is a2:
                continue
            if b1.padded(-pad).overlaps(b2.padded(-pad)):
                issues.append((n1, n2, 0))
    if verbose:
        for it in issues:
            print("  OVERLAP:", it)
        print(f"  overlap check: {len(issues)} issue(s)")
    return issues


def arrow_axes(ax, xmax, ymax, x0=0.0, y0=0.0):
    """Arnott/Cassidy-style axes: arrow heads at the ends of the two spines."""
    ax.plot([xmax], [y0], ">", color=INK, ms=4, clip_on=False, gid="ref")
    ax.plot([x0], [ymax], "^", color=INK, ms=4, clip_on=False, gid="ref")
