"""Shared calibration journal figure style. Edit this file to restyle every figure."""
import matplotlib as mpl

import polish_style as P
BLUE, ORANGE, TEAL, PURPLE = P.ACCENT, P.INK, P.MID, P.DARK
INK, GRAY, MUTED, LIGHT, WHITE = P.INK, P.MID, P.DARK, P.LIGHT, P.WHITE

def style():
    P.apply()

def panel(ax, letter, title):
    ax.set_title(f'({letter})  {title}', loc='left', pad=9, fontweight='normal')

def save_figure(fig, stem, output):
    from pathlib import Path
    import matplotlib.pyplot as plt
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    paths = []
    for ext in ('pdf', 'svg', 'png'):
        path = output / f'{stem}.{ext}'
        fig.savefig(path, dpi=600, bbox_inches=None, pad_inches=0, facecolor=WHITE)
        paths.append(str(path))
    audit_text_layout(fig, stem, output)
    plt.close(fig)
    return paths

def audit_text_layout(fig, stem, output):
    """Conservative text-box screen; every candidate needs visual review."""
    import json
    from pathlib import Path
    from matplotlib.text import Text
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    labels = []
    seen = set()
    outside_ticks = set()
    for ax in fig.axes:
        for axis in (ax.xaxis, ax.yaxis):
            low, high = sorted(axis.get_view_interval())
            for tick in list(axis.get_major_ticks()) + list(axis.get_minor_ticks()):
                if tick.get_loc() < low-1e-10 or tick.get_loc() > high+1e-10:
                    outside_ticks.update((id(tick.label1), id(tick.label2)))
    for item in fig.findobj(match=Text):
        if not item.get_visible() or not item.get_text().strip() or id(item) in seen or id(item) in outside_ticks:
            continue
        seen.add(id(item))
        # Call Text's implementation so annotation arrows do not count as text.
        box = Text.get_window_extent(item, renderer=renderer)
        if box.width <= 0 or box.height <= 0:
            continue
        labels.append({'text': item.get_text(), 'font_pt': item.get_fontsize(),
                       'bbox_px': list(box.extents)})
    intersections = []
    for i, first in enumerate(labels):
        a = first['bbox_px']
        for second in labels[i+1:]:
            b = second['bbox_px']
            dx = min(a[2], b[2]) - max(a[0], b[0])
            dy = min(a[3], b[3]) - max(a[1], b[1])
            if dx > .5 and dy > .5:
                intersections.append({'first': first['text'], 'second': second['text'],
                                      'intersection_px': [dx, dy]})
    from _paths import OUT as _OUT
    qa = _OUT / 'qa'
    qa.mkdir(parents=True, exist_ok=True)
    report = {'figure': stem, 'text_boxes': len(labels), 'candidate_text_intersections': intersections,
              'figure_facecolor': list(fig.get_facecolor()),
              'axes_facecolors': [list(ax.get_facecolor()) for ax in fig.axes],
              'notes': 'Bounding boxes conservatively screen text collisions; inspect images and data/legend interactions separately.'}
    (qa / f'{stem}.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
