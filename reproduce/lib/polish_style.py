"""Shared figure style for the QVDFE figures (trial restyle, 24 Sep).

Where the rules come from
  figures4papers, scientific-figure-making/references/design-theory.md (ChenLiu-1996; its Helvetica rule is replaced by
  Times New Roman at the authors' request, 24 Sep):
    Helvetica/Arial sans-serif; top and right spines off; frameless legends kept out of the data;
    data lines heavier than the axes; minimal or no grid; white background; vector PDF/SVG with
    editable text; 300-600 dpi PNG; hatching or fills that survive greyscale printing; one
    semantic palette (anchor blue #0F4D92, neutrals #CFCECE/#767676/#4D4D4D/#272727).
  paper-craft-skills, paper-comic "paper-figure" style (zsyggg):
    white or very light background; black/dark-grey primary with one or two accents; clean,
    vector-like modules.  (Its image-generation workflow is not used: journal figures stay code-drawn.)
  The authors' standing rules (Cassidy style, memory cassidy-style-feedback):
    black/grey line work with at most one accent colour, direct labels, filled vs open markers,
    no notes inside figures, and no text over curves (checked programmatically).
Where the sources disagree, the authors' rules win: figures4papers' multi-colour semantic palette is
reduced to its neutrals plus its anchor blue as the single accent.

Sizes are for the printed figure: every figure is drawn at the text width (7.07 in, cas-sc) and
included at \\linewidth, so the text sizes below are the printed sizes.
"""
import os
import warnings
import matplotlib as mpl
from matplotlib import font_manager

ACCENT = "#0F4D92"     # the one accent (figures4papers anchor blue)
INK = "#272727"        # primary line work
DARK = "#4D4D4D"
MID = "#767676"
LIGHT = "#CFCECE"
PALE = "#F4F4F4"
WHITE = "#FFFFFF"

# Font: Times New Roman with STIX math, as in the text and tables (user, 24 Sep; replaces the figures4papers
# Helvetica/Arial rule so that figures, tables and text use one typeface)
SERIF = ["Times New Roman", "STIXGeneral", "DejaVu Serif"]
TEXT_WIDTH_IN = 7.07

RC = {
    "font.family": "serif", "font.serif": SERIF,
    "mathtext.fontset": "stix",
    "font.size": 8.5, "axes.labelsize": 8.5, "axes.titlesize": 9, "axes.titlelocation": "left",
    "axes.titleweight": "normal", "axes.titlepad": 6,
    "xtick.labelsize": 7.5, "ytick.labelsize": 7.5, "legend.fontsize": 7.5,
    "axes.linewidth": 0.8, "xtick.major.width": 0.8, "ytick.major.width": 0.8,
    "xtick.major.size": 3, "ytick.major.size": 3, "xtick.direction": "out", "ytick.direction": "out",
    "lines.linewidth": 1.6, "lines.markersize": 4, "lines.solid_capstyle": "round",
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": False,
    "axes.edgecolor": INK, "axes.labelcolor": INK, "xtick.color": INK, "ytick.color": INK, "text.color": INK,
    "legend.frameon": False, "legend.handlelength": 1.8,
    "figure.facecolor": WHITE, "axes.facecolor": WHITE, "savefig.facecolor": WHITE,
    "savefig.edgecolor": WHITE, "figure.edgecolor": WHITE,
    "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none", "savefig.dpi": 600,
    "hatch.linewidth": 0.5, "axes.axisbelow": True,
    "axes.prop_cycle": mpl.cycler(color=[INK, ACCENT, MID, DARK]),
}


def apply():
    # The manuscript uses Times New Roman. A public checkout must also render on
    # systems where that proprietary font is unavailable. An explicit override
    # is validated rather than silently substituted.
    requested = os.environ.get("QVDFE_FIGURE_FONT")
    candidates = [requested] if requested else SERIF
    chosen = None
    for candidate in candidates:
        try:
            font_manager.fontManager.findfont(candidate, fallback_to_default=False)
            chosen = candidate
            break
        except ValueError:
            continue
    if chosen is None:
        raise ValueError("Requested figure font is unavailable: " + str(requested))
    if not requested and chosen != "Times New Roman":
        warnings.warn("Times New Roman is unavailable; figures use " + chosen +
                      ". Numerical values are unchanged; exact paper layout may differ.", stacklevel=2)
    mpl.rcParams.update(RC)
    mpl.rcParams["font.serif"] = [chosen] + [name for name in SERIF if name != chosen]
